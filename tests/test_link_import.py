"""Импорт по ссылке с любой площадки (решение владельца 14.08).

Два изменения разом: ссылки принимаются откуда угодно, а не только с YouTube и
SoundCloud, и подписка нужна на ЛЮБУЮ ссылку, а не только на пачку. Загрузка
своим файлом остаётся бесплатной и без лимитов — там работу делает Telegram, а
по ссылке качаем и перекодируем мы, на единственном ядре.
"""
from app.services.link_import import (
    collect_entries,
    drm_service_name,
    extract_url,
    looks_like_bulk,
)


def test_extract_url_from_message():
    assert extract_url("вот трек https://bandcamp.com/track/x послушай") == (
        "https://bandcamp.com/track/x"
    )
    # Хвостовая пунктуация в ссылку не входит
    assert extract_url("держи https://vk.com/audio123.") == "https://vk.com/audio123"
    assert extract_url("просто текст без ссылки") is None


def test_drm_services_are_recognised():
    """Файла у этих площадок нет ни у нас, ни у yt-dlp — только зашифрованный
    поток. Ссылку туда надо не ронять с ошибкой, а уводить в «Перенос»."""
    assert drm_service_name("https://open.spotify.com/playlist/abc") == "Spotify"
    assert drm_service_name("https://music.apple.com/ru/album/x") == "Apple Music"
    assert drm_service_name("https://music.yandex.ru/album/1") == "Яндекс.Музыка"
    assert drm_service_name("https://www.deezer.com/track/1") == "Deezer"
    # Обычные площадки к DRM не относятся — их качаем как раньше
    assert drm_service_name("https://bandcamp.com/track/x") is None
    assert drm_service_name("https://soundcloud.com/a/b") is None


def test_bulk_detected_by_link_shape():
    """Решение «пачка или один трек» принимается до похода в сеть: разбор через
    yt-dlp — это секунды ожидания, а ответить человеку надо сразу."""
    assert looks_like_bulk("https://bandcamp.com/album/best-of")
    assert looks_like_bulk("https://example.com/playlist/42")
    assert looks_like_bulk("https://vk.com/artist/kizaru")
    assert not looks_like_bulk("https://bandcamp.com/track/one-song")


def test_collect_entries_walks_nested_playlists():
    info = {
        "entries": [
            {"url": "https://x/1", "title": "Первый"},
            {"entries": [{"url": "https://x/2", "title": "Второй"}]},
            {"url": "https://x/1", "title": "Дубль"},  # тот же url — не повторяем
        ]
    }
    entries = collect_entries(info)
    assert [e.url for e in entries] == ["https://x/1", "https://x/2"]
    assert entries[0].title == "Первый"


def test_collect_entries_survives_empty_answer():
    assert collect_entries({}) == []
    assert collect_entries({"entries": []}) == []


def test_entry_without_title_falls_back_to_url():
    entries = collect_entries({"entries": [{"url": "https://x/3"}]})
    assert entries[0].title == "https://x/3"
