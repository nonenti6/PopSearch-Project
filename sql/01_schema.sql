-- PopSearch | 01_schema.sql
-- Выполнять в НОВОЙ ПУСТОЙ базе PostgreSQL popsearch.
-- Предметная область: исполнители поп-музыки; pop не хранится отдельным жанром.
BEGIN;

CREATE TABLE artists (
    artist_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stage_name VARCHAR(150) NOT NULL UNIQUE,
    full_name VARCHAR(200),
    country VARCHAR(100),
    bio TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Все записи являются поджанрами общей предметной области pop.
CREATE TABLE subgenres (
    subgenre_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE albums (
    album_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    artist_id BIGINT NOT NULL REFERENCES artists(artist_id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    release_year SMALLINT CHECK (release_year BETWEEN 1900 AND 2100),
    UNIQUE (artist_id, title)
);

CREATE TABLE album_subgenres (
    album_id BIGINT NOT NULL REFERENCES albums(album_id) ON DELETE CASCADE,
    subgenre_id BIGINT NOT NULL REFERENCES subgenres(subgenre_id) ON DELETE CASCADE,
    PRIMARY KEY (album_id, subgenre_id)
);

CREATE TABLE songs (
    song_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    release_year SMALLINT CHECK (release_year BETWEEN 1900 AND 2100)
);

-- Песня может входить в несколько альбомов; альбом содержит много песен.
CREATE TABLE album_songs (
    album_id BIGINT NOT NULL REFERENCES albums(album_id) ON DELETE CASCADE,
    song_id BIGINT NOT NULL REFERENCES songs(song_id) ON DELETE CASCADE,
    PRIMARY KEY (album_id, song_id)
);

-- Только постоянная подборка источников, НЕ автоматическая лента новостей.
CREATE TABLE materials (
    material_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    artist_id BIGINT NOT NULL REFERENCES artists(artist_id) ON DELETE CASCADE,
    kind VARCHAR(10) NOT NULL CHECK (kind IN ('article', 'video', 'image')),
    title VARCHAR(250) NOT NULL,
    description TEXT,
    source_name VARCHAR(150),
    source_url TEXT NOT NULL CHECK (source_url ~ '^https?://'),
    published_on DATE,
    UNIQUE (kind, source_url)
);

CREATE INDEX idx_albums_artist ON albums(artist_id);
CREATE INDEX idx_materials_artist_kind ON materials(artist_id, kind);
CREATE INDEX idx_songs_title_lower ON songs(lower(title));

-- Правило 1. По поджанру альбома выводим поджанровую связь исполнителя.
CREATE VIEW v_inferred_artist_subgenres AS
SELECT DISTINCT a.artist_id, a.stage_name, sg.subgenre_id,
       sg.name AS subgenre_name, 'subgenre_via_album'::text AS rule_name
FROM artists a
JOIN albums al ON al.artist_id = a.artist_id
JOIN album_subgenres ag ON ag.album_id = al.album_id
JOIN subgenres sg ON sg.subgenre_id = ag.subgenre_id;

-- Правило 2. Песня альбома входит в дискографию исполнителя
-- (не означает, что артист единственный исполнитель композиции).
CREATE VIEW v_inferred_artist_songs AS
SELECT DISTINCT a.artist_id, a.stage_name, s.song_id,
       s.title AS song_title, 'song_via_album'::text AS rule_name
FROM artists a
JOIN albums al ON al.artist_id = a.artist_id
JOIN album_songs als ON als.album_id = al.album_id
JOIN songs s ON s.song_id = als.song_id;

-- Правило 3. По поджанру альбома выводим тематическую связь песни.
CREATE VIEW v_inferred_song_subgenres AS
SELECT DISTINCT s.song_id, s.title AS song_title, sg.subgenre_id,
       sg.name AS subgenre_name, 'subgenre_via_album'::text AS rule_name
FROM songs s
JOIN album_songs als ON als.song_id = s.song_id
JOIN album_subgenres ag ON ag.album_id = als.album_id
JOIN subgenres sg ON sg.subgenre_id = ag.subgenre_id;

COMMIT;
