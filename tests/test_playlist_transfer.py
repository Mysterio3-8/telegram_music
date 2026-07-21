import json

import pytest

from app.db.models import Track, User
from app.services.playlist_transfer import parsers
from app.services.playlist_transfer.parsers import (
    TransferItem,
    TransferSourceError,
    detect_service,
    parse_spotify_html,
    parse_text_list,
    parse_yandex_json,
    yandex_api_url,
)
from app.services.playlist_transfer.service import find_in_catalog, transfer_playlist


def test_detect_service():
    assert detect_service("https://open.spotify.com/playlist/abc") == "spotify"
    assert detect_service("https://music.yandex.ru/users/x/playlists/3") == "yandex"
    assert detect_service("https://vk.com/music/playlist/1_2") == "vk"
    assert detect_service("https://soundcloud.com/user/track") == "soundcloud"
    assert detect_service("https://example.com") is None


def test_parse_text_list_variants():
    items = parse_text_list(
        "1. Kizaru — Fendi\n"
        "Big Baby Tape - Gimme the Loot\n"
        "   \n"
        "Платина – Рок-н-роллер\n"
        "строка без разделителя"
    )

    assert [(i.artist, i.title) for i in items] == [
        ("Kizaru", "Fendi"),
        ("Big Baby Tape", "Gimme the Loot"),
        ("Платина", "Рок-н-роллер"),
    ]


def test_parse_text_list_dedupes():
    items = parse_text_list("A — B\na — b")

    assert len(items) == 1


def test_yandex_api_url():
    url = yandex_api_url("https://music.yandex.ru/users/ilya/playlists/1003")

    assert "owner=ilya" in url and "kinds=1003" in url


def test_yandex_api_url_rejects_garbage():
    with pytest.raises(TransferSourceError):
        yandex_api_url("https://music.yandex.ru/album/123")


def test_parse_yandex_json():
    payload = {
        "playlist": {
            "tracks": [
                {"title": "Fendi", "artists": [{"name": "Kizaru"}]},
                {"title": "", "artists": [{"name": "X"}]},  # без названия — пропуск
            ]
        }
    }

    items = parse_yandex_json(payload)

    assert [(i.artist, i.title) for i in items] == [("Kizaru", "Fendi")]


def test_parse_spotify_html():
    data = {
        "props": {
            "tracks": [
                {"name": "Gimme the Loot", "artists": [{"name": "Big Baby Tape"}]},
            ]
        }
    }
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'

    items = parse_spotify_html(html)

    assert [(i.artist, i.title) for i in items] == [("Big Baby Tape", "Gimme the Loot")]


def test_parse_spotify_html_without_payload():
    assert parse_spotify_html("<html></html>") == []


async def test_find_in_catalog_ignores_case_and_spaces(session):
    session.add(Track(title="Fendi", artist="Kizaru", duration=180))
    await session.commit()

    found = await find_in_catalog(session, TransferItem("  KIZARU ", "fendi"))

    assert found is not None


async def test_transfer_adds_existing_tracks_without_download(session):
    session.add(User(telegram_id=555, first_name="Ivan"))
    session.add(Track(title="Fendi", artist="Kizaru", duration=180))
    await session.commit()

    report = await transfer_playlist(
        session,
        bot=None,
        items=[TransferItem("Kizaru", "Fendi"), TransferItem("Nobody", "Nothing")],
        telegram_id=555,
        download_missing=False,
    )

    assert report.total == 2
    assert report.matched == 1
    assert report.downloaded == 0
    assert report.failed == 1
    assert "Nobody Nothing" in report.failed_examples


async def test_transfer_downloads_missing(session, monkeypatch):
    session.add(User(telegram_id=555, first_name="Ivan"))
    await session.commit()
    calls = []

    class FakeEntry:
        video_id = "vid12345678"

    async def fake_import(session_, bot_, video_id, telegram_id):
        calls.append((video_id, telegram_id))
        return None, True

    monkeypatch.setattr(
        "app.services.playlist_transfer.service.search_first_video", lambda q: FakeEntry()
    )
    monkeypatch.setattr("app.services.playlist_transfer.service.process_user_import", fake_import)

    report = await transfer_playlist(
        session, bot=None, items=[TransferItem("Kizaru", "Fendi")], telegram_id=555
    )

    assert report.downloaded == 1
    assert calls == [("vid12345678", 555)]
