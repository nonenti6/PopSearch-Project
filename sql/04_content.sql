-- PopSearch | 04_content.sql | Полное наполнение базы с упрощённой моделью.
-- Выполнять после 01_schema.sql и 02_seed.sql в новой базе popsearch.

BEGIN;

-- 1. Исполнители: обновляем описания и добавляем отсутствующих.
INSERT INTO artists(stage_name,full_name,country,bio) VALUES
  ('Dua Lipa', 'Dua Lipa', 'Великобритания', 'Британская певица и автор песен албанского происхождения; известна альбомами Future Nostalgia и Radical Optimism.'),
  ('Taylor Swift', 'Taylor Alison Swift', 'США', 'Американская певица и автор песен; её дискография включает поп-альбомы 1989 и Midnights.'),
  ('Billie Eilish', 'Billie Eilish Pirate Baird O’Connell', 'США', 'Американская певица и автор песен; выпустила альбомы WHEN WE ALL FALL ASLEEP, WHERE DO WE GO? и HIT ME HARD AND SOFT.'),
  ('Ariana Grande', 'Ariana Grande-Butera', 'США', 'Американская певица и актриса, известная поп- и R&B-записями, в том числе thank u, next и eternal sunshine.'),
  ('Lady Gaga', 'Stefani Joanne Angelina Germanotta', 'США', 'Американская певица, автор песен и актриса; известна альбомами The Fame и Born This Way.'),
  ('Katy Perry', 'Katheryn Elizabeth Hudson', 'США', 'Американская поп-певица, выпустившая альбомы Teenage Dream и PRISM.'),
  ('Olivia Rodrigo', 'Olivia Isabel Rodrigo', 'США', 'Американская певица и автор песен; её дебютный альбом SOUR вышел в 2021 году, GUTS — в 2023 году.'),
  ('The Weeknd', 'Abel Makkonen Tesfaye', 'Канада', 'Канадский певец и автор песен; известен альбомами After Hours и Dawn FM.'),
  ('Bruno Mars', 'Peter Gene Hernandez', 'США', 'Американский певец, автор песен и продюсер; известен альбомами Doo-Wops & Hooligans и 24K Magic.'),
  ('Sabrina Carpenter', 'Sabrina Annlynn Carpenter', 'США', 'Американская певица и актриса; выпустила альбомы emails i can’t send и Short n’ Sweet.')
ON CONFLICT(stage_name) DO UPDATE SET full_name=EXCLUDED.full_name, country=EXCLUDED.country, bio=EXCLUDED.bio;

-- 2. Альбомы (2 на артиста).
INSERT INTO albums(artist_id,title,release_year)
SELECT a.artist_id, v.title, v.release_year FROM (VALUES
  ('Dua Lipa', 'Future Nostalgia', 2020),
  ('Dua Lipa', 'Radical Optimism', 2024),
  ('Taylor Swift', '1989', 2014),
  ('Taylor Swift', 'Midnights', 2022),
  ('Billie Eilish', 'HIT ME HARD AND SOFT', 2024),
  ('Billie Eilish', 'WHEN WE ALL FALL ASLEEP, WHERE DO WE GO?', 2019),
  ('Ariana Grande', 'eternal sunshine', 2024),
  ('Ariana Grande', 'thank u, next', 2019),
  ('Lady Gaga', 'The Fame', 2008),
  ('Lady Gaga', 'Born This Way', 2011),
  ('Katy Perry', 'Teenage Dream', 2010),
  ('Katy Perry', 'PRISM', 2013),
  ('Olivia Rodrigo', 'SOUR', 2021),
  ('Olivia Rodrigo', 'GUTS', 2023),
  ('The Weeknd', 'After Hours', 2020),
  ('The Weeknd', 'Dawn FM', 2022),
  ('Bruno Mars', '24K Magic', 2016),
  ('Bruno Mars', 'Doo-Wops & Hooligans', 2010),
  ('Sabrina Carpenter', 'Short n’ Sweet', 2024),
  ('Sabrina Carpenter', 'emails i can’t send', 2022)
) AS v(artist,title,release_year) JOIN artists a ON a.stage_name=v.artist
ON CONFLICT(artist_id,title) DO UPDATE SET release_year=EXCLUDED.release_year;

-- 3. Связи альбомов с поджанрами.
INSERT INTO album_subgenres(album_id,subgenre_id)
SELECT al.album_id,g.subgenre_id FROM (VALUES
  ('Dua Lipa', 'Future Nostalgia', 'dance-pop'),
  ('Dua Lipa', 'Radical Optimism', 'dance-pop'),
  ('Taylor Swift', '1989', 'synth-pop'),
  ('Taylor Swift', 'Midnights', 'synth-pop'),
  ('Billie Eilish', 'HIT ME HARD AND SOFT', 'electropop'),
  ('Billie Eilish', 'WHEN WE ALL FALL ASLEEP, WHERE DO WE GO?', 'electropop'),
  ('Ariana Grande', 'eternal sunshine', 'dance-pop'),
  ('Ariana Grande', 'thank u, next', 'dance-pop'),
  ('Lady Gaga', 'The Fame', 'dance-pop'),
  ('Lady Gaga', 'Born This Way', 'dance-pop'),
  ('Katy Perry', 'Teenage Dream', 'dance-pop'),
  ('Katy Perry', 'PRISM', 'dance-pop'),
  ('Olivia Rodrigo', 'SOUR', 'pop-rock'),
  ('Olivia Rodrigo', 'GUTS', 'pop-rock'),
  ('The Weeknd', 'After Hours', 'synth-pop'),
  ('The Weeknd', 'Dawn FM', 'synth-pop'),
  ('Bruno Mars', '24K Magic', 'funk-pop'),
  ('Bruno Mars', 'Doo-Wops & Hooligans', 'funk-pop'),
  ('Sabrina Carpenter', 'Short n’ Sweet', 'dance-pop'),
  ('Sabrina Carpenter', 'emails i can’t send', 'dance-pop')
) AS v(artist,album,genre) JOIN artists a ON a.stage_name=v.artist JOIN albums al ON al.artist_id=a.artist_id AND al.title=v.album JOIN subgenres g ON g.name=v.genre
ON CONFLICT DO NOTHING;

-- 4. Песни. В текущей схеме songs.title НЕ UNIQUE, поэтому используем NOT EXISTS.
INSERT INTO songs(title,release_year)
SELECT v.title,v.release_year FROM (VALUES
  ('Levitating', 2020),
  ('Don’t Start Now', 2019),
  ('Houdini', 2023),
  ('Blank Space', 2014),
  ('Style', 2014),
  ('Anti-Hero', 2022),
  ('BIRDS OF A FEATHER', 2024),
  ('LUNCH', 2024),
  ('bad guy', 2019),
  ('we can''t be friends (wait for your love)', 2024),
  ('yes, and?', 2024),
  ('7 rings', 2019),
  ('Poker Face', 2008),
  ('Just Dance', 2008),
  ('Born This Way', 2011),
  ('Firework', 2010),
  ('California Gurls', 2010),
  ('Roar', 2013),
  ('drivers license', 2021),
  ('good 4 u', 2021),
  ('vampire', 2023),
  ('Blinding Lights', 2019),
  ('Save Your Tears', 2020),
  ('Take My Breath', 2021),
  ('24K Magic', 2016),
  ('That’s What I Like', 2016),
  ('Just the Way You Are', 2010),
  ('Espresso', 2024),
  ('Please Please Please', 2024),
  ('Nonsense', 2022)
) AS v(title,release_year)
WHERE NOT EXISTS (SELECT 1 FROM songs s WHERE s.title=v.title);

-- 5. Привязка треков к альбомам (первый подходящий song_id).
INSERT INTO album_songs(album_id,song_id)
SELECT al.album_id,s.song_id FROM (VALUES
  ('Dua Lipa', 'Future Nostalgia', 'Levitating'),
  ('Dua Lipa', 'Future Nostalgia', 'Don’t Start Now'),
  ('Dua Lipa', 'Radical Optimism', 'Houdini'),
  ('Taylor Swift', '1989', 'Blank Space'),
  ('Taylor Swift', '1989', 'Style'),
  ('Taylor Swift', 'Midnights', 'Anti-Hero'),
  ('Billie Eilish', 'HIT ME HARD AND SOFT', 'BIRDS OF A FEATHER'),
  ('Billie Eilish', 'HIT ME HARD AND SOFT', 'LUNCH'),
  ('Billie Eilish', 'WHEN WE ALL FALL ASLEEP, WHERE DO WE GO?', 'bad guy'),
  ('Ariana Grande', 'eternal sunshine', 'we can''t be friends (wait for your love)'),
  ('Ariana Grande', 'eternal sunshine', 'yes, and?'),
  ('Ariana Grande', 'thank u, next', '7 rings'),
  ('Lady Gaga', 'The Fame', 'Poker Face'),
  ('Lady Gaga', 'The Fame', 'Just Dance'),
  ('Lady Gaga', 'Born This Way', 'Born This Way'),
  ('Katy Perry', 'Teenage Dream', 'Firework'),
  ('Katy Perry', 'Teenage Dream', 'California Gurls'),
  ('Katy Perry', 'PRISM', 'Roar'),
  ('Olivia Rodrigo', 'SOUR', 'drivers license'),
  ('Olivia Rodrigo', 'SOUR', 'good 4 u'),
  ('Olivia Rodrigo', 'GUTS', 'vampire'),
  ('The Weeknd', 'After Hours', 'Blinding Lights'),
  ('The Weeknd', 'After Hours', 'Save Your Tears'),
  ('The Weeknd', 'Dawn FM', 'Take My Breath'),
  ('Bruno Mars', '24K Magic', '24K Magic'),
  ('Bruno Mars', '24K Magic', 'That’s What I Like'),
  ('Bruno Mars', 'Doo-Wops & Hooligans', 'Just the Way You Are'),
  ('Sabrina Carpenter', 'Short n’ Sweet', 'Espresso'),
  ('Sabrina Carpenter', 'Short n’ Sweet', 'Please Please Please'),
  ('Sabrina Carpenter', 'emails i can’t send', 'Nonsense')
) AS v(artist,album,song) JOIN artists a ON a.stage_name=v.artist JOIN albums al ON al.artist_id=a.artist_id AND al.title=v.album JOIN LATERAL (SELECT song_id FROM songs WHERE title=v.song ORDER BY song_id LIMIT 1) s ON TRUE
ON CONFLICT DO NOTHING;

-- 6. Материалы: 10 статей, 10 видео-ссылок (часть поисковых), 10 галерей изображений.
INSERT INTO materials(artist_id,kind,title,description,source_name,source_url,published_on)
SELECT a.artist_id,v.kind,v.title,v.description,v.source_name,v.source_url,v.published_on::date FROM (VALUES
  ('Dua Lipa', 'article', 'Dua Lipa — биография и дискография', 'Справочная статья об исполнителе. Данные статьи при необходимости сверяйте с первичными источниками.', 'Wikipedia', 'https://en.wikipedia.org/wiki/Dua_Lipa', NULL),
  ('Taylor Swift', 'article', 'Taylor Swift — биография и дискография', 'Справочная статья об исполнителе. Данные статьи при необходимости сверяйте с первичными источниками.', 'Wikipedia', 'https://en.wikipedia.org/wiki/Taylor_Swift', NULL),
  ('Billie Eilish', 'article', 'Billie Eilish — биография и дискография', 'Справочная статья об исполнителе. Данные статьи при необходимости сверяйте с первичными источниками.', 'Wikipedia', 'https://en.wikipedia.org/wiki/Billie_Eilish', NULL),
  ('Ariana Grande', 'article', 'Ariana Grande — биография и дискография', 'Справочная статья об исполнителе. Данные статьи при необходимости сверяйте с первичными источниками.', 'Wikipedia', 'https://en.wikipedia.org/wiki/Ariana_Grande', NULL),
  ('Lady Gaga', 'article', 'Lady Gaga — биография и дискография', 'Справочная статья об исполнителе. Данные статьи при необходимости сверяйте с первичными источниками.', 'Wikipedia', 'https://en.wikipedia.org/wiki/Lady_Gaga', NULL),
  ('Katy Perry', 'article', 'Katy Perry — биография и дискография', 'Справочная статья об исполнителе. Данные статьи при необходимости сверяйте с первичными источниками.', 'Wikipedia', 'https://en.wikipedia.org/wiki/Katy_Perry', NULL),
  ('Olivia Rodrigo', 'article', 'Olivia Rodrigo — биография и дискография', 'Справочная статья об исполнителе. Данные статьи при необходимости сверяйте с первичными источниками.', 'Wikipedia', 'https://en.wikipedia.org/wiki/Olivia_Rodrigo', NULL),
  ('The Weeknd', 'article', 'The Weeknd — биография и дискография', 'Справочная статья об исполнителе. Данные статьи при необходимости сверяйте с первичными источниками.', 'Wikipedia', 'https://en.wikipedia.org/wiki/The_Weeknd', NULL),
  ('Bruno Mars', 'article', 'Bruno Mars — биография и дискография', 'Справочная статья об исполнителе. Данные статьи при необходимости сверяйте с первичными источниками.', 'Wikipedia', 'https://en.wikipedia.org/wiki/Bruno_Mars', NULL),
  ('Sabrina Carpenter', 'article', 'Sabrina Carpenter — биография и дискография', 'Справочная статья об исполнителе. Данные статьи при необходимости сверяйте с первичными источниками.', 'Wikipedia', 'https://en.wikipedia.org/wiki/Sabrina_Carpenter', NULL),
  ('Dua Lipa', 'video', 'Levitating — анимационный официальный клип', 'Официальный анимационный клип на песню Levitating.', 'YouTube', 'https://www.youtube.com/watch?v=N000qglmmY0', NULL),
  ('Taylor Swift', 'video', 'Blank Space — официальный клип', 'Официальный музыкальный клип Blank Space.', 'YouTube', 'https://www.youtube.com/watch?v=e-ORhEE9VVg', NULL),
  ('Billie Eilish', 'video', 'Поиск официальных клипов Billie Eilish', 'Ссылка на поиск YouTube, а не на отдельный клип.', 'YouTube', 'https://www.youtube.com/results?search_query=Billie+Eilish+official+music+video', NULL),
  ('Ariana Grande', 'video', 'Поиск официальных клипов Ariana Grande', 'Ссылка на поиск YouTube, а не на отдельный клип.', 'YouTube', 'https://www.youtube.com/results?search_query=Ariana+Grande+official+music+video', NULL),
  ('Lady Gaga', 'video', 'Поиск официальных клипов Lady Gaga', 'Ссылка на поиск YouTube, а не на отдельный клип.', 'YouTube', 'https://www.youtube.com/results?search_query=Lady+Gaga+official+music+video', NULL),
  ('Katy Perry', 'video', 'Firework — официальный клип', 'Официальный музыкальный клип Firework.', 'YouTube', 'https://www.youtube.com/watch?v=QGJuMBdaqIw', NULL),
  ('Olivia Rodrigo', 'video', 'Поиск официальных клипов Olivia Rodrigo', 'Ссылка на поиск YouTube, а не на отдельный клип.', 'YouTube', 'https://www.youtube.com/results?search_query=Olivia+Rodrigo+official+music+video', NULL),
  ('The Weeknd', 'video', 'Blinding Lights — официальный клип', 'Официальный музыкальный клип Blinding Lights.', 'YouTube', 'https://www.youtube.com/watch?v=4NRXx6U8ABQ', NULL),
  ('Bruno Mars', 'video', '24K Magic — официальный клип', 'Официальный музыкальный клип 24K Magic.', 'YouTube', 'https://www.youtube.com/watch?v=UqyT8IEBkvY', NULL),
  ('Sabrina Carpenter', 'video', 'Espresso — страница официального клипа', 'Официальная переходная страница музыкального видео Espresso.', 'Официальная страница артиста', 'https://sabrinacarpenter.bio.to/EspressoOMV', NULL),
  ('Dua Lipa', 'image', 'Dua Lipa — изображения в Wikimedia Commons', 'Поисковая галерея изображений. Это НЕ прямая ссылка на файл; лицензию каждого фото проверяйте отдельно.', 'Wikimedia Commons', 'https://commons.wikimedia.org/w/index.php?search=Dua%20Lipa%20musician&title=Special:MediaSearch&type=image', NULL),
  ('Taylor Swift', 'image', 'Taylor Swift — изображения в Wikimedia Commons', 'Поисковая галерея изображений. Это НЕ прямая ссылка на файл; лицензию каждого фото проверяйте отдельно.', 'Wikimedia Commons', 'https://commons.wikimedia.org/w/index.php?search=Taylor%20Swift%20musician&title=Special:MediaSearch&type=image', NULL),
  ('Billie Eilish', 'image', 'Billie Eilish — изображения в Wikimedia Commons', 'Поисковая галерея изображений. Это НЕ прямая ссылка на файл; лицензию каждого фото проверяйте отдельно.', 'Wikimedia Commons', 'https://commons.wikimedia.org/w/index.php?search=Billie%20Eilish%20musician&title=Special:MediaSearch&type=image', NULL),
  ('Ariana Grande', 'image', 'Ariana Grande — изображения в Wikimedia Commons', 'Поисковая галерея изображений. Это НЕ прямая ссылка на файл; лицензию каждого фото проверяйте отдельно.', 'Wikimedia Commons', 'https://commons.wikimedia.org/w/index.php?search=Ariana%20Grande%20musician&title=Special:MediaSearch&type=image', NULL),
  ('Lady Gaga', 'image', 'Lady Gaga — изображения в Wikimedia Commons', 'Поисковая галерея изображений. Это НЕ прямая ссылка на файл; лицензию каждого фото проверяйте отдельно.', 'Wikimedia Commons', 'https://commons.wikimedia.org/w/index.php?search=Lady%20Gaga%20musician&title=Special:MediaSearch&type=image', NULL),
  ('Katy Perry', 'image', 'Katy Perry — изображения в Wikimedia Commons', 'Поисковая галерея изображений. Это НЕ прямая ссылка на файл; лицензию каждого фото проверяйте отдельно.', 'Wikimedia Commons', 'https://commons.wikimedia.org/w/index.php?search=Katy%20Perry%20musician&title=Special:MediaSearch&type=image', NULL),
  ('Olivia Rodrigo', 'image', 'Olivia Rodrigo — изображения в Wikimedia Commons', 'Поисковая галерея изображений. Это НЕ прямая ссылка на файл; лицензию каждого фото проверяйте отдельно.', 'Wikimedia Commons', 'https://commons.wikimedia.org/w/index.php?search=Olivia%20Rodrigo%20musician&title=Special:MediaSearch&type=image', NULL),
  ('The Weeknd', 'image', 'The Weeknd — изображения в Wikimedia Commons', 'Поисковая галерея изображений. Это НЕ прямая ссылка на файл; лицензию каждого фото проверяйте отдельно.', 'Wikimedia Commons', 'https://commons.wikimedia.org/w/index.php?search=The%20Weeknd%20musician&title=Special:MediaSearch&type=image', NULL),
  ('Bruno Mars', 'image', 'Bruno Mars — изображения в Wikimedia Commons', 'Поисковая галерея изображений. Это НЕ прямая ссылка на файл; лицензию каждого фото проверяйте отдельно.', 'Wikimedia Commons', 'https://commons.wikimedia.org/w/index.php?search=Bruno%20Mars%20musician&title=Special:MediaSearch&type=image', NULL),
  ('Sabrina Carpenter', 'image', 'Sabrina Carpenter — изображения в Wikimedia Commons', 'Поисковая галерея изображений. Это НЕ прямая ссылка на файл; лицензию каждого фото проверяйте отдельно.', 'Wikimedia Commons', 'https://commons.wikimedia.org/w/index.php?search=Sabrina%20Carpenter%20musician&title=Special:MediaSearch&type=image', NULL)
) AS v(artist,kind,title,description,source_name,source_url,published_on) JOIN artists a ON a.stage_name=v.artist
ON CONFLICT(kind,source_url) DO UPDATE SET artist_id=EXCLUDED.artist_id,title=EXCLUDED.title,description=EXCLUDED.description,source_name=EXCLUDED.source_name;
COMMIT;
