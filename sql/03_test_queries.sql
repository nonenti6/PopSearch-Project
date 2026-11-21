-- PopSearch | 03_test_queries.sql
-- Проверка после выполнения 01_schema.sql и 02_seed.sql.

-- Должны существовать все семь физических таблиц.
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
  AND table_name IN (
      'artists', 'subgenres', 'albums', 'album_subgenres',
      'songs', 'album_songs', 'materials'
  )
ORDER BY table_name;

-- Должны существовать все три представления для вывода знаний.
SELECT table_name
FROM information_schema.views
WHERE table_schema = 'public'
  AND table_name IN (
      'v_inferred_artist_subgenres',
      'v_inferred_artist_songs',
      'v_inferred_song_subgenres'
  )
ORDER BY table_name;

-- Должно быть пять поджанров и ни одного pop.
SELECT name, description FROM subgenres ORDER BY name;

-- Пока нет содержимого, запрос должен вернуть 0 строк без ошибки.
SELECT stage_name, subgenre_name, rule_name
FROM v_inferred_artist_subgenres
ORDER BY stage_name, subgenre_name;
