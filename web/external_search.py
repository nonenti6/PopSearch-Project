import re
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import requests
from music_catalogs import (
    TTL, norm, json_get, get_mb_artist, itunes_artist, itunes_search, classify,
    matching_itunes_tracks, search_external_songs, is_pop_label,
)
from wikipedia_media import wiki_summary, wikidata_public_profile, commons_photos

_CACHE = {}
_CACHE_LOCK = threading.Lock()
_MULTI_CACHE = {}
_MULTI_CACHE_LOCK = threading.Lock()
_MULTI_TTL = 10 * 60
_MAX_MULTI_CACHE = 128


def collect_for_artist(artist_name, *, trusted_local=False, max_items=60, card_only=False):
    """Строгая фильтрация ПОП ПЕРЕД возвращением материалов."""
    warnings = []
    if card_only and not trusted_local:
        try:
            quick_artist = itunes_artist(artist_name)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            quick_artist = None
        if (quick_artist and norm(quick_artist.get('artistName')) == norm(artist_name)
                and classify([], quick_artist.get('primaryGenreName'))[0]):
            name = quick_artist['artistName']
            wiki = wiki_summary(name, artist_only=True)
            return {'status': 'allowed', 'artist_name': name,
                    'genres': classify([], quick_artist.get('primaryGenreName'))[1],
                    'artists': [{'stage_name': name, 'country': None,
                                 'bio': (wiki or {}).get('description') or 'Музыкальный исполнитель',
                                 'portrait_url': (wiki or {}).get('image'),
                                 'url': (wiki or {}).get('url') or quick_artist.get('artistLinkUrl'),
                                 'origin': 'external'}],
                    'albums': [], 'songs': [], 'materials': []}
    profile = wikidata_public_profile(artist_name) if re.search(r'[А-Яа-яЁё]', artist_name) else None
    info = profile
    ai = None
    if not profile:
        try:
            info = get_mb_artist(artist_name)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            warnings.append('MusicBrainz временно недоступен')
        try:
            ai = itunes_artist((info or {}).get('name') or artist_name)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            warnings.append('Каталог iTunes временно недоступен')
    # Нельзя подтверждать жанр случайного совпадения из iTunes/Wikipedia.
    # Для обычного поиска обязательно идентифицировать исполнителя по имени.
    # Поиск песен вызывается отдельно, после проверки названия композиции.
    query_key = norm(artist_name)
    if info and not profile and not (query_key in norm(info.get('name'))):
        info = None
    if ai and not (query_key in norm(ai.get('artistName'))):
        ai = None
    genre = ai.get('primaryGenreName') if ai else None
    # MusicBrainz/iTunes иногда сообщают лишь «Alternative», хотя у артиста
    # в Wikidata есть точная жанровая метка «pop music» / «alternative pop».
    # Wikipedia используется для поиска идентификатора, не для догадок по тексту.
    resolved = (info or {}).get('name') or (ai or {}).get('artistName') or artist_name
    wiki = wiki_summary((profile or {}).get('catalog_name') or resolved, artist_only=True)
    allowed, evidence = classify(info.get('genres', []) if info else [], genre)
    if profile and wiki and wiki.get('wikidata_id') != profile['wikidata_id']:
        wiki = None
    if wiki and not profile:
        wiki_name = wiki['title'].split(' (', 1)[0]
        same_name = norm(wiki_name) == norm(resolved)
        if not allowed or not same_name or re.search(r'\brussian\b', wiki.get('description', '')[:350], re.IGNORECASE):
            wiki_profile = wikidata_public_profile(wiki_name, wiki.get('wikidata_id')) if wiki.get('wikidata_id') else None
            same_catalog_id = bool(ai and wiki_profile and wiki_profile.get('itunes_id') == ai.get('artistId')
                                   and ai.get('artistId'))
            if wiki_profile and (same_name or same_catalog_id):
                profile = wiki_profile
                allowed, evidence = classify((info or {}).get('genres', []) + profile['genres'], genre)
            elif wiki_profile and not allowed and not trusted_local:
                # A longer matching name is a separate candidate, with its own catalog identity.
                profile = wiki_profile
                resolved = profile['name']
                ai = None
                info = None
                allowed, evidence = classify(profile['genres'])
            elif not same_name:
                wiki = None
    if not allowed and not trusted_local and not re.search(r'[А-Яа-яЁё]', artist_name):
        profile = wikidata_public_profile(artist_name)
        if profile:
            resolved = profile['name']
            if wiki and wiki.get('wikidata_id') != profile['wikidata_id']:
                wiki = None
            ai = None
            info = None
            allowed, evidence = classify(profile['genres'])
    if not allowed and not trusted_local:
        warning = ('Связь исполнителя с поп-музыкой не подтверждена по доступным метаданным.'
                   if info or ai or wiki else 'Исполнитель не найден во внешних каталогах.')
        return {'status': 'unverified', 'artist_name': artist_name,
                'genres': (info or {}).get('genres', []) + ([genre] if genre else []),
                'warning': warning,
                'artists': [], 'albums': [], 'songs': [], 'materials': [], 'news_artist': None}
    if card_only:
        picture = (profile or {}).get('image') or (wiki or {}).get('image')
        return {'status': 'allowed', 'artist_name': resolved, 'genres': evidence,
                'artists': [{'stage_name': resolved, 'country': None,
                             'bio': (wiki or {}).get('description') or 'Музыкальный исполнитель',
                             'portrait_url': picture,
                             'url': (wiki or {}).get('url') or (info or {}).get('url'),
                             'origin': 'external'}],
                'albums': [], 'songs': [], 'materials': []}
    artist_id = (profile or {}).get('itunes_id') or (ai or {}).get('artistId')
    albums, songs = [], []
    try:
        if artist_id:
            # Один запрос получает точные записи артиста по идентификатору.
            data = json_get('https://itunes.apple.com/lookup', params={
                'id': artist_id, 'entity': 'song', 'limit': min(200, max(70, max_items * 3)), 'country': 'US'})
            records = [x for x in (data.get('results') or []) if
                       x.get('wrapperType') == 'track' and x.get('artistId') == artist_id]
        else:
            catalog_name = (profile or {}).get('catalog_name') or resolved
            records = itunes_search(catalog_name, 'song', min(200, max(70, max_items * 3)))
            names = {norm(resolved), norm(catalog_name)}
            records = [x for x in records if norm(x.get('artistName')) in names]
        seen_tracks, seen_albums = set(), set()
        for r in records:
            track_name = r.get('trackName')
            collection = r.get('collectionName')
            if track_name and norm(track_name) not in seen_tracks:
                seen_tracks.add(norm(track_name))
                songs.append({'song_title': track_name, 'stage_name': resolved,
                              'url': r.get('trackViewUrl'), 'preview_url': r.get('previewUrl'),
                              'album_title': collection, 'album_id': r.get('collectionId'), 'release_year': (r.get('releaseDate') or '')[:4],
                              'cover_url': r.get('artworkUrl100'), 'cover_source': r.get('collectionViewUrl'),
                              'source': 'iTunes / Apple Music', 'origin': 'external'})
            if collection and norm(collection) not in seen_albums and r.get('collectionType', '') != 'Single':
                seen_albums.add(norm(collection))
                albums.append({'title': collection, 'release_year': (r.get('releaseDate') or '')[:4],
                               'stage_name': resolved, 'cover_url': r.get('artworkUrl100'),
                               'cover_source': r.get('collectionViewUrl'), 'origin': 'external'})
    except (requests.RequestException, ValueError, TypeError, KeyError):
        warnings.append('Не удалось загрузить всю дискографию')
    picture = (profile or {}).get('image') or (wiki or {}).get('image')
    materials = []
    publications = (profile or {}).get('publications', ())
    for title, source, url in publications:
        materials.append({'kind': 'article', 'title': title, 'source_name': source,
                          'source_url': url, 'stage_name': resolved, 'origin': 'external'})
    if not publications and wiki and wiki.get('url'):
        materials.append({'kind': 'article', 'title': wiki['title'],
                          'description': wiki['description'] or 'Биографическая статья',
                          'source_name': 'Wikipedia', 'source_url': wiki['url'],
                          'stage_name': resolved, 'origin': 'external'})
    if picture:
        materials.append({'kind': 'image', 'title': f'{resolved} — фотография',
                          'description': 'Изображение из статьи Wikipedia; проверьте лицензию оригинала.',
                          'source_name': 'Wikipedia / Wikimedia Commons', 'source_url': picture,
                          'page_url': (profile or {}).get('image_page') or (wiki or {}).get('url') or picture,
                          'stage_name': resolved, 'is_direct_image': True, 'origin': 'external'})
    for photo in commons_photos(resolved, limit=min(200, max_items), wikidata_id=(profile or {}).get('wikidata_id') or (wiki or {}).get('wikidata_id')):
        if photo['source_url'] != picture:
            materials.append(photo)
    localized_news_name = (profile or {}).get('news_name') or ''
    news_name = localized_news_name if re.search(r'[А-Яа-яЁё]', localized_news_name) else resolved
    return {'status': 'allowed', 'artist_name': resolved, 'genres': evidence or (['pop · локальная база знаний'] if trusted_local else []),
            'warning': '; '.join(warnings) if warnings else None,
            'artists': [{'stage_name': resolved, 'country': None,
                         'bio': (wiki or {}).get('description') or 'Музыкальный исполнитель',
                         'portrait_url': picture, 'url': (wiki or {}).get('url') or (info or {}).get('url'),
                         'origin': 'external'}],
            'albums': albums[:max_items], 'songs': songs[:max_items], 'materials': materials,
            'news_artist': resolved, 'news_name': news_name,
            'artist_query': artist_name if profile else resolved}


def resolve_artists_from_media(query):
    """Находим исполнителей только по достаточно конкретному названию записи.

    Не трактуем короткий запрос имени («jack», «finn») как случайный трек.
    Внешние каталоги возвращают много нерелевантных песен, поэтому
    принимаем только полное совпадение нормализованного названия.
    """
    candidates = []
    query_key = norm(query)
    if len(query_key) < 5:
        return []
    for entity, key in [('song', 'trackName'), ('album', 'collectionName')]:
        try:
            matches = (matching_itunes_tracks(query) if entity == 'song'
                       else itunes_search(query, entity, 80))
            for item in matches:
                name = item.get('artistName') or ''
                title = item.get(key) or ''
                if (name and name.casefold() != 'various artists'
                        and (query_key == norm(title))
                        and norm(name) not in {norm(n) for n in candidates}):
                    candidates.append(name)
        except (requests.RequestException, ValueError, TypeError):
            continue
    return candidates[:8]


def resolve_artist_from_media(query):
    """Обратная совместимость с прежними тестами."""
    artists = resolve_artists_from_media(query)
    return artists[0] if artists else None


def _artist_name_matches_query(query, artist_name):
    """Проверяет вхождение значимой подстроки запроса в имя артиста (не в названия песен).

    Минимум 3 алфавитно-цифровых символа отсекают слишком широкие совпадения.
    Для включения в выдачу всё равно требуется независимое подтверждение поп-жанра.
    """
    key = norm(query)
    name_key = norm(artist_name)
    return len(key) >= 3 and key in name_key


def discover_artist_names(query, *, max_candidates=12):
    """Ищет несколько профилей артиста; сам факт обнаружения не подтверждает поп-жанр.

    Использует независимые каталоги, чтобы сбой одного сервиса не сводил поиск
    к первому попавшемуся совпадению. Возвращает только имена, без непроверенных карточек.
    """
    if not _artist_name_matches_query(query, query) or len(norm(query)) < 3:
        return []
    candidates = []
    seen = set()

    def add(name):
        if (name and _artist_name_matches_query(query, name)
                and norm(name) not in seen):
            seen.add(norm(name))
            candidates.append(name)

    # Сначала ищем в Wikidata на языке запроса. Для имён на латинице также
    # используем английский, чтобы находить артистов вне локального каталога.
    langs = ('ru', 'en') if re.search(r'[А-Яа-яЁё]', query) else ('en',)
    wd_names = []
    for language in langs:
        try:
            data = json_get('https://www.wikidata.org/w/api.php', params={
                'action': 'wbsearchentities', 'search': query,
                'language': language, 'limit': 50, 'format': 'json'})
            for item in data.get('search') or []:
                description = item.get('description') or ''
                if re.search(r'пев|музыкант|групп|вокал|исполнител|'
                             r'singer|musician|band|duo|rapper|vocalist|'
                             r'pop star|record producer', description, re.I):
                    name = item.get('label') or ''
                    if _artist_name_matches_query(query, name):
                        wd_names.append(name)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            pass

    itunes_names = []
    try:
        for item in itunes_search(query, 'musicArtist', 200):
            name = item.get('artistName') or ''
            if _artist_name_matches_query(query, name):
                itunes_names.append(name)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    # Чередуем результаты из разных источников вместо взятия первых N из одного каталога.
    # Это не даёт большому списку малоизвестных совпадений перекрыть известного
    # артиста из другого каталога.
    for index in range(max(len(wd_names), len(itunes_names))):
        if index < len(wd_names):
            add(wd_names[index])
        if index < len(itunes_names):
            add(itunes_names[index])
        if len(candidates) >= max_candidates:
            break
    return candidates[:max_candidates]


def search_matching_artists(query, *, existing_names=(), max_artists=10):
    """Параллельно проверяет кандидатов с сохранением исходного порядка каталога.

    Обнаружение не доказывает жанр. Каждая карточка проходит единую явную
    проверку поп-метаданных — без исключений для отдельных артистов и записи в БД.
    """
    if len(re.findall(r'\w+', query, re.UNICODE)) != 1 or len(norm(query)) < 3:
        return []
    known = {norm(name) for name in existing_names}
    key = norm(query)
    now = time.monotonic()
    with _MULTI_CACHE_LOCK:
        cached = _MULTI_CACHE.get(key)
        if cached and now - cached[0] < _MULTI_TTL:
            candidates = cached[1]
        else:
            candidates = None

    if candidates is None:
        names = discover_artist_names(query, max_candidates=16)

        def check(name):
            try:
                result = collect_for_artist(name, card_only=True)
            except (requests.RequestException, ValueError, KeyError, TypeError):
                return []
            if not result or result.get('status') != 'allowed':
                return []
            return [artist for artist in result.get('artists', [])
                    if _artist_name_matches_query(query, artist.get('stage_name', ''))]


        with ThreadPoolExecutor(max_workers=8) as executor:
            groups = executor.map(check, names)
            candidates = [artist for group in groups for artist in group]
        with _MULTI_CACHE_LOCK:
            if len(_MULTI_CACHE) >= _MAX_MULTI_CACHE:
                _MULTI_CACHE.pop(next(iter(_MULTI_CACHE)))
            _MULTI_CACHE[key] = (time.monotonic(), candidates)

    verified = []
    for artist in candidates:
        name_key = norm(artist.get('stage_name'))
        if name_key and name_key not in known:
            verified.append(dict(artist))
            known.add(name_key)
            if len(verified) >= max_artists:
                break
    return verified


def search_external(query, *, trusted_local=False, max_items=60, artist_only=False, card_only=False):
    """Нет жанрового подтверждения = не выдаём внешние данные (fail closed)."""
    key = (norm(query), bool(trusted_local), min(200, max_items), artist_only, card_only)
    if not key:
        return None
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached:
            timestamp, result = cached
            ttl = 60 if artist_only and (not result or result['status'] != 'allowed') else TTL
            if time.monotonic() - timestamp < ttl:
                return result
    result = collect_for_artist(query, trusted_local=trusted_local, max_items=max_items,
                                card_only=card_only)
    # Не отклоняем подтверждённого поп-артиста только потому, что MusicBrainz/iTunes
    # вернули полное имя при поиске по фамилии. Раньше при отсутствии профиля
    # в Wikidata требовалось совпадение *всего* имени целиком.
    if artist_only and result['status'] == 'allowed' and not _artist_name_matches_query(
            query, result['artist_name']):
        result = None
    if not artist_only and result['status'] != 'allowed' and not trusted_local and len(norm(query)) >= 5:
        # Если это название песни/альбома, проверяем каждого кандидата,
        # а не первого попавшегося артиста с совпадающим названием.
        for candidate in resolve_artists_from_media(query):
            if norm(candidate) == norm(query):
                continue
            option = collect_for_artist(candidate, max_items=max_items)
            if option['status'] != 'allowed':
                continue
            songs = [x for x in option['songs'] if norm(query) == norm(x['song_title'])]
            albums = [x for x in option['albums'] if norm(query) == norm(x['title'])]
            if songs or albums:
                option['songs'], option['albums'] = songs, albums
                option['matched_song_title'] = bool(songs)
                result = option
                break
    with _CACHE_LOCK:
        if len(_CACHE) > 150:
            _CACHE.clear()
        _CACHE[key] = (time.monotonic(), result)
    return result
