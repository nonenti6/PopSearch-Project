import os
from contextlib import contextmanager
from urllib.parse import urlparse, parse_qs
import psycopg
from psycopg.rows import dict_row
from music_catalogs import norm, is_pop_label

@contextmanager
def database():
    conn = psycopg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432')),
        dbname=os.getenv('DB_NAME', 'popsearch'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', ''),
        row_factory=dict_row,
        connect_timeout=5,
    )
    try:
        yield conn
    finally:
        conn.close()


def youtube_id(url):
    """Извлечь ID только из допустимых URL YouTube."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https':
            return None
        if host in ('youtube.com', 'www.youtube.com', 'm.youtube.com') and parsed.path == '/watch':
            video_id = parse_qs(parsed.query).get('v', [''])[0]
        elif host == 'youtu.be':
            video_id = parsed.path.strip('/')
        else:
            return None
        if len(video_id) == 11 and all(c.isalnum() or c in '_-' for c in video_id):
            return video_id
    except (ValueError, TypeError):
        return None
    return None


def resolve_news_artist(cur, query):
    # Связь запроса с исполнителем из БЗ.
    cur.execute('''
        SELECT stage_name FROM (
            SELECT stage_name, 0 AS priority FROM artists
            WHERE stage_name ILIKE %s
            UNION ALL
            SELECT stage_name, 1 FROM artists
            WHERE stage_name ILIKE %s
            UNION ALL
            SELECT a.stage_name, 2 FROM albums al
            JOIN artists a ON a.artist_id=al.artist_id
            WHERE al.title ILIKE %s
            UNION ALL
            SELECT stage_name, 3 FROM v_inferred_artist_songs
            WHERE song_title ILIKE %s
        ) AS matches
        ORDER BY priority, stage_name LIMIT 1
    ''', (query, f'%{query}%', f'%{query}%', f'%{query}%'))
    artist = cur.fetchone()
    return artist['stage_name'] if artist else None


def load_local_results(query, artist_search, pattern, query_key):
    """Загружает локальные сущности (артистов, альбомы, песни, медиа) за одно подключение к БД."""
    results = {"artists": [], "albums": [], "songs": [], "materials": []}
    news_artist = None
    with database() as conn, conn.cursor() as cur:
        news_artist = None if artist_search else resolve_news_artist(cur, query)
        cur.execute('''
            SELECT artist_id, stage_name, country, bio
            FROM artists
            WHERE stage_name ILIKE %s OR full_name ILIKE %s OR bio ILIKE %s
            ORDER BY stage_name LIMIT 30
        ''', (pattern, pattern, pattern))
        results['artists'] = cur.fetchall()
        if artist_search:
            results['artists'] = [
                item for item in results['artists'] if norm(item['stage_name']) == query_key
            ]
            news_artist = next((item['stage_name'] for item in results['artists']), None)
        if results['artists']:
            artist_ids = [a['artist_id'] for a in results['artists']]
            cur.execute('''
                SELECT DISTINCT ON (artist_id) artist_id, source_url
                FROM materials
                WHERE kind = 'image' AND artist_id = ANY(%s)
                ORDER BY artist_id, material_id
            ''', (artist_ids,))
            portrait_by_id = {m['artist_id']: m['source_url'] for m in cur.fetchall()}
            for artist in results['artists']:
                artist['portrait_url'] = portrait_by_id.get(artist['artist_id'])
        cur.execute('''
            SELECT al.title, al.release_year, a.stage_name
            FROM albums al JOIN artists a ON a.artist_id = al.artist_id
            WHERE (NOT %s AND al.title ILIKE %s) OR a.stage_name ILIKE %s
            ORDER BY a.stage_name, al.release_year DESC LIMIT 40
        ''', (artist_search, pattern, pattern))
        results['albums'] = cur.fetchall()
        # Представление — правило вывода принадлежности песни дискографии артиста.
        cur.execute('''
            SELECT DISTINCT song_id, song_title, stage_name, rule_name, s.release_year
            FROM v_inferred_artist_songs JOIN songs s USING (song_id)
            WHERE (NOT %s AND song_title ILIKE %s) OR stage_name ILIKE %s
            ORDER BY stage_name, song_title
        ''', (artist_search, pattern, pattern))
        results['songs'] = cur.fetchall()
        cur.execute('''
            SELECT m.kind, m.title, m.description, m.source_name,
                   m.source_url, a.stage_name
            FROM materials m JOIN artists a ON a.artist_id = m.artist_id
            WHERE (NOT %s AND (m.title ILIKE %s OR m.description ILIKE %s))
                   OR a.stage_name ILIKE %s
            ORDER BY a.stage_name, m.kind, m.title LIMIT 60
        ''', (artist_search, pattern, pattern, pattern))
        results['materials'] = cur.fetchall()
        for material in results['materials']:
            material['youtube_id'] = youtube_id(material['source_url']) if material['kind'] == 'video' else None
            material['is_direct_image'] = (
                material['kind'] == 'image'
                and urlparse(material['source_url']).hostname in ('commons.wikimedia.org', 'upload.wikimedia.org')
                and ('/Special:FilePath/' in material['source_url'] or 'upload.wikimedia.org' in material['source_url'])
            )
    return results, news_artist


def trusted_pop_artists(candidate_names):
    """Возвращает известных в локальной БД поп-артистов из представления выведенных жанров."""
    if not candidate_names:
        return set()
    with database() as conn, conn.cursor() as cur:
        cur.execute('''
            SELECT DISTINCT stage_name, subgenre_name
            FROM v_inferred_artist_subgenres
            WHERE lower(stage_name) = ANY(%s)
        ''', (candidate_names,))
        return {row['stage_name'] for row in cur.fetchall()
                if is_pop_label(row['subgenre_name'])}


def albums_for_songs(song_ids):
    """Возвращает альбомы, связанные с найденными локальными песнями."""
    if not song_ids:
        return []
    with database() as conn, conn.cursor() as cur:
        cur.execute('''
            SELECT DISTINCT al.title, al.release_year, a.stage_name
            FROM album_songs link
            JOIN albums al USING (album_id)
            JOIN artists a USING (artist_id)
            WHERE link.song_id = ANY(%s)
            ORDER BY a.stage_name, al.release_year DESC, al.title
        ''', (song_ids,))
        return cur.fetchall()


def local_album_years(albums):
    """Ищет в локальной БД известные годы выпуска для альбомов без этих метаданных."""
    if not albums:
        return {}
    names = sorted({album['stage_name'].lower() for album in albums})
    titles = sorted({album['title'].lower() for album in albums})
    with database() as conn, conn.cursor() as cur:
        cur.execute('''
            SELECT a.stage_name, al.title, al.release_year
            FROM albums al JOIN artists a USING (artist_id)
            WHERE lower(a.stage_name) = ANY(%s)
              AND lower(al.title) = ANY(%s)
              AND al.release_year IS NOT NULL
        ''', (names, titles))
        return {(row['stage_name'].lower(), row['title'].lower()): row['release_year']
                for row in cur.fetchall()}
