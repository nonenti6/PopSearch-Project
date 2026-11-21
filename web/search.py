import logging
from urllib.parse import urlparse
import psycopg
import requests
from album_covers import attach_album_art
from database import load_local_results, trusted_pop_artists, albums_for_songs, local_album_years
from external_search import search_external, search_matching_artists
from music_catalogs import (
    norm, matching_itunes_tracks, search_external_songs, is_pop_label,
    itunes_album_years,
)
from wikipedia_media import attach_artist_portraits
from news_search import fetch_news
from video_search import find_artist_videos

def search_results(query, artist_search=False, category="all", show=20, logger=None):
    logger = logger or logging.getLogger(__name__)
    category = 'publications' if category in ('article', 'news') else category
    if category not in ('all', 'artists', 'albums', 'songs', 'publications', 'video', 'image'):
        category = 'all'

    # Все вкладки получают одинаковый набор данных; меняется только отображение.
    try:
        show = int(show)
    except (ValueError, TypeError):
        show = 20
    show = min(200, max(20, ((show + 9) // 10) * 10))
    source_limit = min(200, max(60, show * 3))
    results = {'artists': [], 'albums': [], 'songs': [], 'materials': []}
    feed = []
    error = None
    news = []
    news_error = None
    news_artist = None
    external_notice = None
    external_genres = []
    external_status = None
    video_has_next = False
    song_search = False
    if query:
        query_key = norm(query)
        pattern = f'%{query}%'
        if artist_search:
            pattern = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        try:
            results, news_artist = load_local_results(query, artist_search, pattern, query_key)
            # Сначала локальные знания, затем внешние. При ошибке внешней сети
            # локальные результаты не теряются. Новых записей в БД не создаём.
            # Точное имя исполнителя и точное название песни могут совпасть.
            title_songs = []
            local_artist_match = any(norm(item['stage_name']) == query_key for item in results['artists'])
            ext = None
            try:
                ext = search_external(
                    query, trusted_local=local_artist_match, max_items=source_limit,
                    artist_only=True, card_only=(category == 'artists'),
                )
            except (requests.RequestException, ValueError, TypeError, KeyError):
                logger.exception('External artist search failed')
                external_notice = 'Поиск исполнителя во внешних источниках временно недоступен.'
            exact_artist_match = local_artist_match or bool(ext and ext['status'] == 'allowed')
            if not artist_search:
                local_title_songs = [
                    item for item in results['songs'] if query_key and query_key in norm(item['song_title'])
                ]
                try:
                    tracks = matching_itunes_tracks(query)
                    candidate_names = sorted({track['artistName'].lower() for track in tracks})
                    trusted_artists = {item['stage_name'] for item in local_title_songs}
                    if exact_artist_match:
                        trusted_artists.add(query)
                    trusted_artists.update(trusted_pop_artists(candidate_names))
                    title_songs = search_external_songs(tracks, trusted_artists=trusted_artists)
                except (requests.RequestException, ValueError, TypeError):
                    logger.exception('External song search failed')
                    external_notice = 'Поиск песен в iTunes временно недоступен.'
                song_search = bool(local_title_songs or title_songs)
            if not (song_search or exact_artist_match or artist_search):
                searched_artist = news_artist or query
                try:
                    ext = search_external(
                        searched_artist, trusted_local=bool(news_artist), max_items=source_limit,
                    )
                except Exception:
                    logger.exception('External sources failed')
                    external_notice = 'Внешние источники временно недоступны; локальная база работает.'
            if not artist_search and not exact_artist_match and ext and ext.get('matched_song_title'):
                title_songs = ext['songs']
                song_search = True
                ext = None
            if song_search:
                if not exact_artist_match:
                    news_artist = None
                    ext = None
                    results.update(albums=[], songs=local_title_songs, materials=[])
                local_albums = albums_for_songs(sorted({song['song_id'] for song in local_title_songs}))
                albums_by_key = {
                    (norm(album['stage_name']), norm(album['title'])): album
                    for album in (*results['albums'], *local_albums)
                }
                for song in title_songs:
                    title = song.get('album_title')
                    if title:
                        name = song['stage_name']
                        album = albums_by_key.setdefault((norm(name), norm(title)), {
                            'title': title, 'stage_name': name, 'origin': 'external',
                        })
                        for field in ('album_id', 'cover_url', 'cover_source'):
                            if song.get(field) and not album.get(field):
                                album[field] = song[field]
                results['albums'] = list(albums_by_key.values())
            if ext:
                external_status = ext['status']
                external_genres = ext.get('genres', [])
                external_notice = external_notice or ext.get('warning')
                if ext['status'] == 'allowed':
                    news_artist = ext.get('news_artist')
                    # Не дублируем один и тот же объект из двух источников.
                    for group, items in [('artists', ext['artists']), ('albums', ext['albums']),
                                         ('materials', ext['materials'])]:
                        for item in items:
                            if group == 'artists':
                                exists = any(norm(a['stage_name']) == norm(item['stage_name']) for a in results[group])
                            elif group == 'albums':
                                exists = any(norm(a['title']) == norm(item['title']) and norm(a['stage_name']) == norm(item['stage_name']) for a in results[group])
                            else:
                                exists = any(a['source_url'] == item['source_url'] for a in results[group])
                            if not exists:
                                results[group].append(item)
            # Частичное имя артиста может совпасть с несколькими подтверждёнными
            # поп-исполнителями. Не заменяем основного артиста и его дискографию/новости —
            # только добавляем карточки остальных.
            if category in ('all', 'artists') and not artist_search:
                try:
                    additional = search_matching_artists(
                        query, existing_names=[a['stage_name'] for a in results['artists']],
                        max_artists=min(12, show))
                    known_names = {norm(a['stage_name']) for a in results['artists']}
                    for artist in additional:
                        name_key = norm(artist['stage_name'])
                        if name_key not in known_names:
                            results['artists'].append(artist)
                            known_names.add(name_key)
                except (requests.RequestException, ValueError, TypeError, KeyError):
                    logger.exception('Multiple artist lookup failed')
            if song_search:
                matching_artists = {norm(item['stage_name']): item for item in results['artists']}
                for song in (*local_title_songs, *title_songs):
                    name = song['stage_name']
                    artist = matching_artists.setdefault(norm(name), {
                        'stage_name': name, 'song_match_only': True,
                    })
                    artist.setdefault('matched_song_title', song['song_title'])
                results['artists'] = list(matching_artists.values())
            if category in ('all', 'songs'):
                artist_catalog_songs = ext['songs'] if ext and ext['status'] == 'allowed' else []
                songs_by_key = {}
                for item in (*results['songs'], *title_songs, *artist_catalog_songs):
                    key = (norm(item['song_title']), norm(item['stage_name']))
                    song = songs_by_key.setdefault(key, dict(item))
                    for field in ('url', 'album_title', 'release_year'):
                        if item.get(field) and not song.get(field):
                            song[field] = item[field]
                results['songs'] = sorted(
                    songs_by_key.values(),
                    key=lambda song: norm(song['song_title']) != query_key,
                )
            # Видео запрашиваем отдельно и только после подтверждения поп-жанра.
            # Не тратим квоту YouTube API на вкладку «Все» и на рок-исполнителей.
            if category == 'video' and ext and ext.get('status') == 'allowed':
                video_items, video_warning, video_has_next = find_artist_videos(
                    ext.get('news_artist') or query, limit=min(200, max(20, show)), with_more=True)
                if video_warning:
                    external_notice = (external_notice + ' ' if external_notice else '') + video_warning
                saved_urls = {m['source_url'] for m in results['materials']}
                for video in video_items:
                    if video['source_url'] not in saved_urls:
                        results['materials'].append(video)
                        saved_urls.add(video['source_url'])
            if news_artist and category in ('all', 'publications'):
                news_limit = 30 if category == 'publications' else min(30, max(20, show))
                news_name = ext.get('news_name') if ext and ext['status'] == 'allowed' else None
                news, news_error = fetch_news(news_name or news_artist, limit=news_limit)
            if song_search and category in ('all', 'albums'):
                preceding_items = (
                    len(results['songs']) + len(news)
                    + sum(not item.get('song_match_only') for item in results['artists'])
                    + sum(item['kind'] == 'article' for item in results['materials'])
                )
                visible_count = show if category == 'albums' else max(0, show - preceding_items)
                missing_year = [
                    album for album in results['albums'][:visible_count]
                    if not album.get('release_year')
                ]
                if missing_year:
                    local_years = local_album_years(missing_year)
                    for album in missing_year:
                        key = (album['stage_name'].lower(), album['title'].lower())
                        album['release_year'] = local_years.get(key)
                    external_years = itunes_album_years(
                        album['album_id'] for album in missing_year
                        if album.get('album_id') and not album['release_year']
                    )
                    for album in missing_year:
                        if not album['release_year']:
                            album['release_year'] = external_years.get(album.get('album_id'))
            if category in ('all', 'albums'):
                attach_album_art([x for x in results['albums'] if not x.get('cover_url')])
        except psycopg.Error:
            logger.exception('Database query failed')
            error = 'Не удалось подключиться к базе данных. Проверьте настройки .env и PostgreSQL.'

    # Артисты, чьи имена содержат запрос пользователя, всегда идут перед песнями
    # и другими медиа. Точные совпадения ранжируются выше совпадений по префиксу и в середине имени.
    if query:
        def artist_rank(artist):
            name = norm(artist.get('stage_name'))
            key = norm(query)
            return (bool(artist.get('song_match_only')),
                    0 if name == key else 1 if name.startswith(key) else 2 if key in name else 3,
                    name)
        results['artists'].sort(key=artist_rank)
    articles = [m for m in results['materials'] if m['kind'] == 'article']
    # Единая лента, без самостоятельных секций «Статьи» и «Новости».
    # Чередование статей и новостей делает выдачу более удобной.
    for item in results['artists']:
        if not item.get('song_match_only'):
            feed.append({'type': 'artist', 'data': item})
    if song_search:
        feed.extend({'type': 'song', 'data': item} for item in results['songs']
                    if norm(item['song_title']) == query_key)
    for index in range(max(len(articles), len(news))):
        if index < len(articles):
            feed.append({'type': 'article', 'data': articles[index]})
        if index < len(news):
            feed.append({'type': 'news', 'data': news[index]})
    music_groups = ('songs', 'albums') if song_search else ('albums', 'songs')
    for group in music_groups:
        for item in results[group]:
            if not (song_search and group == 'songs' and norm(item['song_title']) == query_key):
                feed.append({'type': group[:-1], 'data': item})
    category_items = {
        'all': feed,
        'artists': results['artists'],
        'albums': results['albums'],
        'songs': results['songs'],
        'publications': articles + news,
        'video': [m for m in results['materials'] if m['kind'] == 'video'],
        'image': [m for m in results['materials'] if m['kind'] == 'image'],
    }
    all_items = category_items[category]
    total = len(all_items)
    more_available = show < 200 and (total > show or (category == 'video' and video_has_next))
    if category == 'all':
        feed = feed[:show]
    elif category == 'artists':
        results['artists'] = all_items[:show]
        if song_search:
            attach_artist_portraits(results['artists'])
    elif category == 'albums':
        results['albums'] = all_items[:show]
    elif category == 'songs':
        results['songs'] = all_items[:show]
    elif category in ('video', 'image'):
        results['materials'] = all_items[:show]
    elif category == 'publications':
        articles = articles[:show]
        news = news[:show - len(articles)]
    return dict(query=query, category=category, results=results, feed=feed,
                total=total, show=show, more_available=more_available, error=error,
                articles=articles, news=news, news_error=news_error,
                news_artist=news_artist, external_notice=external_notice,
                external_status=external_status, external_genres=external_genres,
                artist_search=artist_search, song_search=song_search)
