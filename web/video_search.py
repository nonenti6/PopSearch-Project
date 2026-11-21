import os
import re
import threading
import time

import requests

_LOCK = threading.Lock()
_CACHE = {}
_TTL = 1800
_ENDPOINT = 'https://www.googleapis.com/youtube/v3/search'


def _norm(value):
    return re.sub(r'[^\w]+', '', (value or '').casefold())


def find_artist_videos(artist_name, limit=8, *, with_more=False):
    """Возвращает (materials, warning). Вызывать ТОЛЬКО после подтверждения жанра артиста."""
    def pack(items, warning, more=False):
        return (items, warning, more) if with_more else (items, warning)

    key = os.getenv('YOUTUBE_API_KEY', '').strip()
    if not key:
        return pack([], 'Внешний поиск видео отключён: добавьте YOUTUBE_API_KEY в .env. Видео из базы знаний доступны.')
    if not artist_name or not artist_name.strip():
        return pack([], None)
    cache_key = (_norm(artist_name), limit)
    with _LOCK:
        cached = _CACHE.get(cache_key)
        if cached and time.monotonic() - cached[0] < _TTL:
            return pack(cached[1][0], None, cached[1][1])
    materials = []
    seen = set()
    token = _norm(artist_name)
    page_token = None
    more_available = False
    try:
        # YouTube поддерживает продолжение через nextPageToken.
        # Каждая новая страница расходует квоту API.
        for _ in range(min(4, (limit + 19) // 20)):
            params = {
                'key': key, 'part': 'snippet',
                'q': artist_name + ' official music video',
                'type': 'video', 'videoEmbeddable': 'true',
                'videoCategoryId': '10', 'maxResults': 20,
                'order': 'relevance', 'safeSearch': 'moderate',
            }
            if page_token:
                params['pageToken'] = page_token
            response = requests.get(_ENDPOINT, params=params, timeout=(3, 8))
            if response.status_code in (400, 403):
                return pack(materials, 'YouTube API отклонил запрос: проверьте ключ, доступ и квоту.')
            response.raise_for_status()
            payload = response.json()
            for row in payload.get('items', []):
                vid = (row.get('id') or {}).get('videoId', '')
                if not re.fullmatch(r'[A-Za-z0-9_-]{11}', vid) or vid in seen:
                    continue
                snippet = row.get('snippet') or {}
                title = snippet.get('title') or ''
                channel = snippet.get('channelTitle') or ''
                if token not in _norm(title + ' ' + channel):
                    continue
                seen.add(vid)
                materials.append({
                    'kind': 'video', 'title': title[:250],
                    'description': 'Видео из поиска YouTube · канал: ' + channel[:100],
                    'source_name': 'YouTube',
                    'source_url': 'https://www.youtube.com/watch?v=' + vid,
                    'youtube_id': vid, 'stage_name': artist_name,
                    'origin': 'external',
                })
                if len(materials) >= limit:
                    break
            page_token = payload.get('nextPageToken')
            if len(materials) >= limit:
                more_available = bool(page_token)
                break
            if not page_token:
                break
    except (requests.RequestException, ValueError):
        return pack(materials, 'YouTube временно недоступен. Видео из PostgreSQL доступны.')
    with _LOCK:
        if len(_CACHE) > 100:
            _CACHE.clear()
        _CACHE[cache_key] = (time.monotonic(), (materials, bool(page_token)))
    return pack(materials, None, more_available or bool(page_token))
