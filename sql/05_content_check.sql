-- PopSearch | 05_content_check.sql
-- Выполнить после 04_content.sql. Только проверка, базу не изменяет.

-- В чистой базе после первых четырёх файлов должно быть:
-- artists 10, subgenres 5, albums 20, album_subgenres 20,
-- songs 30, album_songs 30, materials 30.
SELECT 'artists' AS object_name, COUNT(*) AS record_count FROM artists
UNION ALL SELECT 'subgenres', COUNT(*) FROM subgenres
UNION ALL SELECT 'albums', COUNT(*) FROM albums
UNION ALL SELECT 'album_subgenres', COUNT(*) FROM album_subgenres
UNION ALL SELECT 'songs', COUNT(*) FROM songs
UNION ALL SELECT 'album_songs', COUNT(*) FROM album_songs
UNION ALL SELECT 'materials', COUNT(*) FROM materials
ORDER BY object_name;

-- 10 статей, 10 видеоссылок, 10 ссылок на галереи изображений.
SELECT kind, COUNT(*) AS record_count
FROM materials
GROUP BY kind
ORDER BY kind;

-- Справочник поджанров (pop не должен присутствовать).
SELECT subgenre_id, name, description FROM subgenres ORDER BY name;

-- Правило 1: поджанры Dua Lipa по её альбомам.
SELECT stage_name, subgenre_name, rule_name
FROM v_inferred_artist_subgenres
WHERE stage_name = 'Dua Lipa'
ORDER BY subgenre_name;

-- Правило 2: песни из дискографии Sabrina Carpenter.
SELECT stage_name, song_title, rule_name
FROM v_inferred_artist_songs
WHERE stage_name = 'Sabrina Carpenter'
ORDER BY song_title;

-- Правило 3: поджанр песни Levitating по альбому.
SELECT song_title, subgenre_name, rule_name
FROM v_inferred_song_subgenres
WHERE song_title = 'Levitating'
ORDER BY subgenre_name;

-- Контроль целостности наполнения: запрос должен вернуть 0 строк.
-- Если строка появилась, она указывает на отсутствующую связь.
SELECT 'album_without_subgenre' AS issue, al.title AS object_name
FROM albums al
WHERE NOT EXISTS (SELECT 1 FROM album_subgenres ag WHERE ag.album_id = al.album_id)
UNION ALL
SELECT 'album_without_song', al.title
FROM albums al
WHERE NOT EXISTS (SELECT 1 FROM album_songs als WHERE als.album_id = al.album_id)
UNION ALL
SELECT 'artist_without_material', a.stage_name
FROM artists a
WHERE NOT EXISTS (SELECT 1 FROM materials m WHERE m.artist_id = a.artist_id);
