import os
import re
import threading
import time
import requests

APP_UA = os.getenv('MUSICBRAINZ_USER_AGENT', 'PopSearch/1.0 (contact: popsearch@example.org)')
_HTTP_LOCAL = threading.local()


def _http_session():
    session = getattr(_HTTP_LOCAL, 'session', None)
    if session is None:
        session = requests.Session()
        session.headers.update({'User-Agent': APP_UA})
        _HTTP_LOCAL.session = session
    return session
TTL = 30 * 60
POP_TAGS = {
    'pop', 'pop music', 'dance-pop', 'dance pop', 'synth-pop', 'synthpop',
    'electropop', 'electro-pop', 'pop-rock', 'pop rock', 'funk-pop', 'funk pop',
    'indie pop', 'indie-pop', 'alternative pop', 'alt-pop', 'art pop',
    'bedroom pop', 'dream pop', 'chamber pop', 'k-pop', 'kpop', 'j-pop',
    'teen pop', 'baroque pop', 'power pop', 'pop soul', 'pop rap',
    'hyperpop', 'sophisti-pop', 'country pop', 'latin pop', 'pop punk',
}
_SONG_CACHE = {}
_SONG_LOCK = threading.Lock()
_MB_LOCK = threading.Lock()
_MB_LAST = 0.0
_MB_UNAVAILABLE_UNTIL = 0.0
_MB_RETRY_SECONDS = 45


def norm(value):
    return re.sub(r'[^\w]+', '', (value or '').casefold(), flags=re.UNICODE)


def json_get(url, *, params=None, timeout=(3, 7), headers=None):
    response = _http_session().get(url, params=params, timeout=timeout, headers=headers)
    response.raise_for_status()
    if len(response.content) > 2_500_000:
        raise ValueError('API response is too large')
    return response.json()


def mb_get(path, params):
    """Глобальный в процессе лимит <= 1 запрос/сек; на нескольких workers нужен общий limiter."""
    global _MB_LAST, _MB_UNAVAILABLE_UNTIL
    with _MB_LOCK:
        if time.monotonic() < _MB_UNAVAILABLE_UNTIL:
            raise requests.ConnectionError('MusicBrainz temporarily unavailable')
        delay = 1.15 - (time.monotonic() - _MB_LAST)
        if delay > 0:
            time.sleep(delay)
        _MB_LAST = time.monotonic()
        try:
            return json_get('https://musicbrainz.org/ws/2/' + path,
                            params={**params, 'fmt': 'json'},
                            headers={'User-Agent': APP_UA})
        except requests.RequestException:
            _MB_UNAVAILABLE_UNTIL = time.monotonic() + _MB_RETRY_SECONDS
            raise


def get_mb_artist(query):
    """Ищем артиста по полному имени или содержащейся в имени части строки."""
    key = norm(query)
    if not key:
        return None
    escaped = re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r'\\\1', query)
    # MusicBrainz/Lucene: запрос в кавычках иногда не возвращает
    # нужного исполнителя, поэтому отдельно запрашиваем префикс.
    # Сначала обычный поиск, затем принудительно префиксный поиск.
    # API может вернуть нерелевантные записи, их проверим локально.
    candidates = []
    last_error = None
    for expression, limit in [(f'artist:"{escaped}"', 25),
                              (f'artist:{escaped}*', 100)]:
        try:
            batch = mb_get('artist/', {'query': expression, 'limit': limit}).get('artists') or []
            seen = {a.get('id') for a in candidates}
            candidates.extend(a for a in batch if a.get('id') not in seen)
        except (requests.RequestException, ValueError, KeyError) as exc:
            last_error = exc
        # Точное совпадение имени лучше неполного; не требуется второй запрос.
        if any(norm(a.get('name')) == key for a in candidates):
            break
    if not candidates and last_error is not None:
        raise last_error
    matches = [a for a in candidates if (
        key == norm(a.get('name')) or
        key == norm(a.get('sort-name')) or
        any(key == norm(alias.get('name')) for alias in a.get('aliases', [])) or
        (len(key) >= 3 and (key in norm(a.get('name')) or
         key in norm(a.get('sort-name')) or
         any(key in norm(alias.get('name')) for alias in a.get('aliases', []))))
    )]
    if not matches:
        return None
    chosen = max(matches, key=lambda a: (
        int(norm(a.get('name')) == key),
        int(a.get('score') or 0),
        int(norm(a.get('name')).startswith(key)), -len(a.get('name') or '')))
    detail = mb_get('artist/' + chosen['id'], {'inc': 'genres+tags'})
    genres = [g.get('name', '') for g in (detail.get('genres') or [])]
    tags = sorted(detail.get('tags') or [], key=lambda t: t.get('count', 0), reverse=True)
    genres += [t.get('name', '') for t in tags[:35]]
    return {'name': detail.get('name') or chosen['name'], 'id': chosen['id'],
            'genres': list(dict.fromkeys(genres)), 'source': 'MusicBrainz',
            'url': 'https://musicbrainz.org/artist/' + chosen['id']}


def itunes_search(term, entity, limit=35):
    data = json_get('https://itunes.apple.com/search', params={
        'term': term, 'media': 'music', 'entity': entity, 'limit': limit, 'country': 'US'})
    return data.get('results') or []


def itunes_artist(query):
    matches = itunes_search(query, 'musicArtist', 25)
    exact = next((a for a in matches if norm(a.get('artistName')) == norm(query)), None)
    if exact:
        return exact
    if len(norm(query)) >= 3:
        return next((a for a in matches if norm(query) in norm(a.get('artistName'))), None)
    return None


def is_pop_label(label):
    name = re.sub(r'[_\s]+', ' ', (label or '').strip().casefold()).replace('–', '-')
    if name in POP_TAGS or name.replace('-', ' ') in POP_TAGS:
        return True
    # Только явная формула '* pop' или 'pop *', не substrings как 'popular'.
    return bool(re.search(r'(?<!\w)pop(?!\w)', name))


def classify(genres, itunes_genre=None):
    labels = list(genres or [])
    if itunes_genre:
        labels.append(itunes_genre)
    positive = sorted({g for g in labels if is_pop_label(g)})
    return bool(positive), positive


def matching_itunes_tracks(query):
    """Получаем точные совпадения один раз для обоих путей поиска."""
    key = norm(query)
    if not key:
        return []
    with _SONG_LOCK:
        cached = _SONG_CACHE.get(key)
        if cached and time.monotonic() - cached[0] < TTL:
            return cached[1]
    tracks = [
        track for track in itunes_search(query, 'song', 200)
        if key in norm(track.get('trackName'))
        and norm(track.get('artistName'))
        and norm(track.get('artistName')) != 'variousartists'
    ]
    with _SONG_LOCK:
        if len(_SONG_CACHE) >= 150:
            _SONG_CACHE.pop(next(iter(_SONG_CACHE)))
        _SONG_CACHE[key] = (time.monotonic(), tracks)
    return tracks


def search_external_songs(query_or_tracks, *, trusted_artists=()):
    tracks = (matching_itunes_tracks(query_or_tracks) if isinstance(query_or_tracks, str)
              else query_or_tracks)
    pop_artists = {norm(name) for name in trusted_artists}
    pop_artists.update(
        norm(track['artistName']) for track in tracks
        if is_pop_label(track.get('primaryGenreName'))
    )
    return [
        {'song_title': track['trackName'], 'stage_name': track['artistName'],
         'url': track.get('trackViewUrl'), 'preview_url': track.get('previewUrl'),
         'album_title': track.get('collectionName'), 'album_id': track.get('collectionId'),
         'cover_url': track.get('artworkUrl100'), 'cover_source': track.get('collectionViewUrl'),
         'release_year': (track.get('releaseDate') or '')[:4],
         'source': 'iTunes / Apple Music', 'origin': 'external'}
        for track in tracks if norm(track['artistName']) in pop_artists
    ]


def itunes_album_years(album_ids):
    ids = sorted(set(album_ids))
    years = {}
    for offset in range(0, len(ids), 50):
        batch = ids[offset:offset + 50]
        try:
            data = json_get('https://itunes.apple.com/lookup', params={
                'id': ','.join(map(str, batch)), 'country': 'US',
            })
        except (requests.RequestException, ValueError, TypeError):
            continue
        for album in data.get('results') or []:
            album_id = album.get('collectionId')
            year = (album.get('releaseDate') or '')[:4]
            if album.get('wrapperType') == 'collection' and album_id in batch and year.isascii() and year.isdigit() and len(year) == 4:
                years[album_id] = int(year)
    return years
