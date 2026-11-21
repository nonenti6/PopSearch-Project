from datetime import datetime, timezone
import re
from email.utils import parsedate_to_datetime
from threading import Lock
from time import monotonic
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

_CACHE = {}
_CACHE_LOCK = Lock()
_CACHE_TTL_SECONDS = 15 * 60
_MAX_RSS_BYTES = 1_000_000
_GOOGLE_NEWS_URL = 'https://news.google.com/rss/search'


def _read_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        return None


def fetch_news(artist_name, *, limit=8):
    """Вернуть (новости, ошибка). Новости обновляются после 15-минутного кеша."""
    name = artist_name.strip()
    if not name:
        return [], None
    now = monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(name.casefold())
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1][:limit], None

    if re.search(r'[А-Яа-яЁё]', name):
        params = {'q': f'"{name}" when:30d', 'hl': 'ru', 'gl': 'RU', 'ceid': 'RU:ru'}
    else:
        params = {
            'q': f'"{name}" (singer OR music OR album OR concert) when:30d',
            'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en',
        }
    try:
        response = requests.get(
            _GOOGLE_NEWS_URL,
            params=params,
            timeout=(3, 6),
            headers={'User-Agent': 'PopSearchCourseProject/1.0 (RSS reader)'},
        )
        response.raise_for_status()
        if len(response.content) > _MAX_RSS_BYTES:
            raise ValueError('Too large RSS feed')
        root = ET.fromstring(response.content)
        if root.tag != 'rss':
            raise ValueError('Unexpected RSS format')
        entries = []
        seen = set()
        for item in root.findall('./channel/item'):
            title = (item.findtext('title') or '').strip()
            link = (item.findtext('link') or '').strip()
            parsed = urlparse(link)
            if not title or parsed.scheme != 'https' or not parsed.netloc:
                continue
            dedup_key = (title.casefold(), link)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            publisher = (item.findtext('./source') or 'Google News').strip()
            pub = _read_date(item.findtext('pubDate'))
            entries.append({
                'title': title,
                'url': link,
                'publisher': publisher,
                'published': pub.strftime('%d.%m.%Y %H:%M UTC') if pub else 'Дата не указана',
                '_sort_date': pub or datetime.min.replace(tzinfo=timezone.utc),
            })
        entries.sort(key=lambda x: x['_sort_date'], reverse=True)
        for item in entries:
            item.pop('_sort_date')
        with _CACHE_LOCK:
            _CACHE[name.casefold()] = (monotonic(), entries[:30])
        return entries[:limit], None
    except (requests.RequestException, ET.ParseError, ValueError) as exc:
        return [], 'Сейчас не удалось загрузить новости. Попробуйте обновить страницу позже.'
