import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from urllib.parse import quote
import requests
from music_catalogs import norm, json_get, classify


def wiki_summary(artist_name, *, artist_only=False):
    """Страница Wikipedia с проверкой совпадения названия. Научно-музыкальные факты не выводятся из статьи."""
    try:
        data = json_get('https://en.wikipedia.org/w/api.php', params={
            'action': 'query', 'generator': 'search', 'gsrsearch': f'intitle:"{artist_name}"',
            'gsrlimit': 5, 'prop': 'extracts|pageimages|info|pageprops', 'inprop': 'url',
            'exintro': 1, 'explaintext': 1, 'pithumbsize': 500, 'ppprop': 'wikibase_item', 'format': 'json'})
        pages = list((data.get('query') or {}).get('pages', {}).values())
        pages.sort(key=lambda p: (norm(p.get('title')) != norm(artist_name), int(p.get('index', 0))))
        for p in pages:
            title = p.get('title') or ''
            if norm(title) == norm(artist_name) or norm(artist_name) in norm(title):
                if artist_only:
                    page_name = title.split(' (', 1)[0]
                    intro = (p.get('extract') or '').split('\n', 1)[0]
                    name_matches = (norm(page_name) == norm(artist_name)
                                    or page_name.casefold().startswith(artist_name.casefold() + ' '))
                    is_artist = re.search(
                        r'\b(?:is|was|are|were)\s+(?:an?\s+)?'
                        r'(?!(?:[\w-]+\s+){0,5}(?:song|album|single|EP|soundtrack)\b)'
                        r'(?:[\w-]+\s+){0,7}'
                        r'(?:singer(?:-songwriter)?|rapper|musician|band|duo|vocalist|DJ|group|'
                        r'songwriter|record producer)\b',
                        intro, flags=re.IGNORECASE,
                    )
                    if not (name_matches and is_artist):
                        continue
                return {'title': title, 'description': (p.get('extract') or '')[:950],
                        'url': p.get('fullurl') or 'https://en.wikipedia.org/wiki/' + quote(title.replace(' ', '_')),
                        'image': (p.get('thumbnail') or {}).get('source'),
                        'wikidata_id': (p.get('pageprops') or {}).get('wikibase_item')}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    return None


@lru_cache(maxsize=512)
def artist_portrait(name):
    return (wiki_summary(name, artist_only=True) or {}).get('image')


def attach_artist_portraits(artists):
    if not artists:
        return
    with ThreadPoolExecutor(max_workers=6) as executor:
        portraits = executor.map(artist_portrait, (artist['stage_name'] for artist in artists))
        for artist, portrait in zip(artists, portraits):
            artist['matched_artist_portrait'] = portrait


def wikidata_artist_genres(wikidata_id, *, claims=None):
    """Жанр исполнителя по утверждению P136 в Wikidata; не по тексту статей.

    При отсутствии метаданных возвращает пустой список, не даёт ложного допуска.
    """
    if not wikidata_id or not re.fullmatch(r'Q[1-9][0-9]{0,15}', wikidata_id):
        return []
    try:
        if claims is None:
            doc = json_get('https://www.wikidata.org/w/api.php', params={
                'action': 'wbgetentities', 'ids': wikidata_id, 'props': 'claims', 'format': 'json'})
            claims = ((doc.get('entities') or {}).get(wikidata_id) or {}).get('claims') or {}
        qids = []
        for claim in claims.get('P136', []):
            value = ((claim.get('mainsnak') or {}).get('datavalue') or {}).get('value') or {}
            entity_id = value.get('id') if isinstance(value, dict) else None
            if entity_id and re.fullmatch(r'Q[1-9][0-9]{0,15}', entity_id):
                qids.append(entity_id)
        if not qids:
            return []
        labels_doc = json_get('https://www.wikidata.org/w/api.php', params={
            'action': 'wbgetentities', 'ids': '|'.join(dict.fromkeys(qids[:25])),
            'props': 'labels', 'languages': 'en', 'format': 'json'})
        return [((labels_doc.get('entities') or {}).get(qid) or {}).get('labels', {}).get('en', {}).get('value', '')
                for qid in qids]
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return []


def commons_thumbnail(filename):
    try:
        doc = json_get('https://commons.wikimedia.org/w/api.php', params={
            'action': 'query', 'titles': 'File:' + filename, 'prop': 'imageinfo',
            'iiprop': 'url', 'iiurlwidth': 500, 'format': 'json',
        })
        for page in (doc.get('query') or {}).get('pages', {}).values():
            image = (page.get('imageinfo') or [{}])[0]
            url = image.get('thumburl') or image.get('url')
            if url and url.startswith('https://'):
                return url
    except (requests.RequestException, ValueError, KeyError, TypeError):
        pass
    return None


def wikidata_public_profile(name, wikidata_id=None):
    """Данные подтверждённого музыканта и ссылки на его источники."""
    api = 'https://www.wikidata.org/w/api.php'
    try:
        if not wikidata_id:
            # По фамилии могут найтись несколько людей. Не отвергаем всю
            # выдачу: последовательно проверяем наиболее релевантных музыкантов.
            search = json_get(api, params={
                'action': 'wbsearchentities', 'search': name, 'language': 'ru',
                'limit': 25, 'format': 'json',
            })
            query_key = norm(name)
            ranked = []
            for position, item in enumerate(search.get('search') or []):
                identifier = item.get('id') or ''
                if not re.fullmatch(r'Q[1-9][0-9]{0,15}', identifier):
                    continue
                description = item.get('description') or ''
                if not re.search(r'пев|музыкант|групп|вокал|исполнител|'
                                 r'singer|musician|band|duo|rapper|vocalist|producer',
                                 description, re.IGNORECASE):
                    continue
                variants = [item.get('label') or '',
                            (item.get('match') or {}).get('text') or '']
                keys = [norm(value) for value in variants if value]
                if not any(query_key == key or
                           (len(query_key) >= 4 and query_key in key)
                           for key in keys):
                    continue
                # Полное имя или псевдоним лучше частичного совпадения,
                # а при равенстве учитываем порядок Wikidata.
                priority = 0 if query_key in keys else 1
                ranked.append((priority, position, identifier))
            ranked.sort()
            if not ranked:
                return None
            identifiers = list(dict.fromkeys(row[2] for row in ranked))
            doc = json_get(api, params={
                'action': 'wbgetentities', 'ids': '|'.join(identifiers),
                'props': 'labels|claims|sitelinks', 'languages': 'ru|en',
                'sitefilter': 'ruwiki|enwiki', 'format': 'json',
            })
            entities = doc.get('entities') or {}
            entity = {}
            for identifier in identifiers:
                candidate = entities.get(identifier) or {}
                if candidate.get('missing') is not None:
                    continue
                genres = wikidata_artist_genres(identifier, claims=candidate.get('claims') or {})
                if classify(genres)[0]:
                    wikidata_id, entity = identifier, candidate
                    break
            if not entity:
                return None
        else:
            if not re.fullmatch(r'Q[1-9][0-9]{0,15}', wikidata_id):
                return None
            doc = json_get(api, params={
                'action': 'wbgetentities', 'ids': wikidata_id,
                'props': 'labels|claims|sitelinks', 'languages': 'ru|en',
                'sitefilter': 'ruwiki|enwiki', 'format': 'json',
            })
            entity = (doc.get('entities') or {}).get(wikidata_id) or {}
        labels = entity.get('labels') or {}
        claims = entity.get('claims') or {}
        genres = wikidata_artist_genres(wikidata_id, claims=claims)
        if not classify(genres)[0]:
            return None
        cyrillic_query = bool(re.search(r'[А-Яа-яЁё]', name))
        russian_origin = any(
            ((claim.get('mainsnak') or {}).get('datavalue') or {}).get('value', {}).get('id') == 'Q159'
            for prop in ('P27', 'P495') for claim in claims.get(prop, [])
            if claim.get('rank') != 'deprecated'
        )
        catalog_name = (labels.get('en') or {}).get('value') or name
        russian_name = (labels.get('ru') or {}).get('value') or name
        news_name = russian_name if cyrillic_query or russian_origin else catalog_name
        language = 'ru' if cyrillic_query or russian_origin else 'en'
        biography = ((entity.get('sitelinks') or {}).get(language + 'wiki') or {}).get('title')
        wikipedia = (f'https://{language}.wikipedia.org/wiki/' + quote(biography.replace(' ', '_'))
                     if biography else None)
        publications = [(f'{news_name} — биография', 'Википедия', wikipedia)] if wikipedia else []
        values = {}
        for prop in ('P18', 'P856', 'P2850'):
            for claim in claims.get(prop, []):
                value = ((claim.get('mainsnak') or {}).get('datavalue') or {}).get('value')
                if claim.get('rank') != 'deprecated' and isinstance(value, str) and value:
                    values[prop] = value
                    break
        website = values.get('P856', '')
        if website.startswith(('https://', 'http://')):
            publications.append(('Официальный сайт', 'Официальный сайт', website))
        picture = values.get('P18')
        apple_id = values.get('P2850', '')
        return {
            'name': russian_name if cyrillic_query else catalog_name,
            'news_name': news_name, 'genres': genres, 'url': wikipedia,
            'wikidata_id': wikidata_id, 'publications': publications,
            'catalog_name': catalog_name,
            'itunes_id': int(apple_id) if re.fullmatch(r'[0-9]{1,18}', apple_id) else None,
            'image': commons_thumbnail(picture) if picture else None,
            'image_page': ('https://commons.wikimedia.org/wiki/File:'
                           + quote(picture.replace(' ', '_'), safe='')) if picture else None,
        }
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def commons_photos(name, limit=60, *, wikidata_id=None):
    """Файлы Commons, у которых исполнитель указан в поле «изображает»."""
    if not wikidata_id or not re.fullmatch(r'Q[1-9][0-9]{0,15}', wikidata_id) or limit <= 0:
        return []
    photos = []
    seen = set()
    continuation = {}
    try:
        for _ in range(8):
            params = {
                'action': 'query', 'generator': 'search',
                'gsrsearch': f'haswbstatement:P180={wikidata_id}', 'gsrnamespace': 6,
                'gsrlimit': 40, 'prop': 'imageinfo',
                'iiprop': 'url|mime|extmetadata', 'iiurlwidth': 640,
                'format': 'json', **continuation,
            }
            data = json_get('https://commons.wikimedia.org/w/api.php', params=params)
            pages = sorted((data.get('query') or {}).get('pages', {}).values(),
                           key=lambda page: page.get('index', 0))
            for page in pages:
                title = page.get('title', '')
                info = (page.get('imageinfo') or [{}])[0]
                if info.get('mime') not in ('image/jpeg', 'image/png', 'image/webp'):
                    continue
                link = info.get('thumburl') or info.get('url')
                page_url = info.get('descriptionurl')
                if not link or not link.startswith('https://'):
                    continue
                if not page_url or not page_url.startswith('https://commons.wikimedia.org/'):
                    continue
                if page_url in seen:
                    continue
                seen.add(page_url)
                license_data = info.get('extmetadata') or {}
                license_name = (license_data.get('LicenseShortName') or {}).get(
                    'value', 'Смотрите условия лицензии')
                photos.append({
                    'kind': 'image',
                    'title': title.removeprefix('File:').replace('_', ' '),
                    'description': 'Фотография Wikimedia Commons · ' + license_name,
                    'source_name': 'Wikimedia Commons', 'source_url': link,
                    'page_url': page_url, 'is_direct_image': True,
                    'stage_name': name, 'origin': 'external',
                })
                if len(photos) >= limit:
                    return photos
            continuation = data.get('continue') or {}
            if not continuation:
                break
    except (requests.RequestException, ValueError, TypeError, KeyError):
        # Если одна из страниц временно недоступна, показываем уже собранное.
        pass
    return photos
