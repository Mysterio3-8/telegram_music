"""Прогрев по списку владельца (21.09): комментарии и продолжение с того же места."""
from app.cli.warmup import mark_done, read_queries, read_state


def _file(tmp_path, text, name="list.txt"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_comments_and_blanks_are_not_queries(tmp_path):
    path = _file(tmp_path, "# заголовок\n\nANNA ASTI Царица\n  # ещё коммент\nJONY Комета\n")
    assert read_queries(path) == ["ANNA ASTI Царица", "JONY Комета"]


def test_limit_takes_first_n(tmp_path):
    path = _file(tmp_path, "a\nb\nc\n")
    assert read_queries(path, limit=2) == ["a", "b"]


def test_done_queries_are_skipped_so_night_moves_on(tmp_path):
    # Без этого ночной прогон каждый раз брал бы первые N строк и находил
    # «уже в базе», не доходя до хвоста списка
    path = _file(tmp_path, "a\nb\nc\nd\n")
    state = str(tmp_path / "done.txt")
    mark_done(state, "a")
    mark_done(state, "B")  # регистр не важен
    assert read_queries(path, limit=2, done=read_state(state)) == ["c", "d"]


def test_state_file_is_created_with_directory(tmp_path):
    state = str(tmp_path / "нет-такой-папки" / "done.txt")
    mark_done(state, "запрос")
    assert read_state(state) == {"запрос"}


def test_missing_state_is_empty(tmp_path):
    assert read_state(None) == set()
    assert read_state(str(tmp_path / "нет.txt")) == set()


def test_artist_list_is_shipped_and_sane():
    # Ночной прогрев греет по именам артистов: их топ-треки спрашиваем у источника,
    # а не берём на веру из списка (21.09: там были выдуманные названия)
    names = read_queries("data/popular-artists.txt")
    assert len(names) > 300
    assert len(set(n.lower() for n in names)) == len(names)  # без дублей
    assert "MACAN" in names and "Taylor Swift" in names


def test_owner_list_is_shipped_and_sane():
    # Файл лежит в репозитории: ночной прогрев берёт его прямо с сервера
    queries = read_queries("data/popular-tracks.txt")
    assert len(queries) > 900
    assert all("|" not in q for q in queries)  # развёрнуто в «исполнитель название»
    assert len(set(q.lower() for q in queries)) == len(queries)  # без дублей


def _unit(name: str) -> str:
    import pathlib

    # encoding обязателен: на Windows read_text() берёт кодировку локали
    return pathlib.Path("deploy") / name, (pathlib.Path("deploy") / name).read_text(encoding="utf-8")


def test_warmup_timer_runs_slow_and_remembers_progress():
    # Темп владельца (21.09): один трек в 30–60 секунд, а не ночной рывок
    _, service = _unit("tg-music-warmup.service")
    assert "--delay 45" in service
    assert "--state /var/lib/tg-music/warmup-artists.done" in service
    assert "--artists data/popular-artists.txt" in service
    assert "MemoryMax" in service  # бокс 961 МБ, прогрев не должен его съесть

    _, timer = _unit("tg-music-warmup.timer")
    assert "OnCalendar=hourly" in timer

    _, install = _unit("install-units.sh")
    assert "tg-music-warmup.timer" in install  # иначе таймер не включится на сервере

    _, nightly = _unit("tg-music-catalog-maintain.service")
    # Ночной рывок по списку артистов убран — он живёт в своём таймере
    assert "--artists data/popular-artists.txt" not in nightly
    assert "--popular 30 --days 7 --delay 45" in nightly
