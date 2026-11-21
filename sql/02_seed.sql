-- PopSearch | 02_seed.sql
-- Небольшой справочник поджанров. Основной жанр pop задаёт предметную область,
-- поэтому отдельной записи pop в subgenres нет.
BEGIN;

INSERT INTO subgenres(name, description) VALUES
    ('dance-pop', 'Танцевальная поп-музыка.'),
    ('synth-pop', 'Поп-музыка с заметным использованием синтезаторов.'),
    ('electropop', 'Поп-музыка с электронным звучанием.'),
    ('pop-rock', 'Сочетание поп- и рок-музыки.'),
    ('funk-pop', 'Поп-музыка с элементами фанка.')
ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description;

COMMIT;
