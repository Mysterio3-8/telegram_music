from app.services.soundcloud import (
    collect_soundcloud_entries,
    extract_soundcloud_url,
    is_soundcloud_link,
    normalize_soundcloud_url,
)


def test_normalize_collapses_profile_tabs():
    # Вкладки профиля (yt-dlp даёт по ним 404) сворачиваются к корню профиля
    assert normalize_soundcloud_url("https://soundcloud.com/ilya-sokruta/popular-tracks") == "https://soundcloud.com/ilya-sokruta"
    assert normalize_soundcloud_url("https://soundcloud.com/user/tracks") == "https://soundcloud.com/user"
    assert normalize_soundcloud_url("https://soundcloud.com/user/likes/") == "https://soundcloud.com/user"
    assert normalize_soundcloud_url("https://soundcloud.com/user/popular-tracks?x=1") == "https://soundcloud.com/user"


def test_normalize_preserves_tracks_and_sets():
    # Реальный трек и конкретный сет трогать нельзя
    assert normalize_soundcloud_url("https://soundcloud.com/user/my-beat") == "https://soundcloud.com/user/my-beat"
    assert normalize_soundcloud_url("https://soundcloud.com/user/sets/my-pack") == "https://soundcloud.com/user/sets/my-pack"
    assert normalize_soundcloud_url("https://soundcloud.com/user") == "https://soundcloud.com/user"


def test_extract_normalizes():
    assert extract_soundcloud_url("глянь soundcloud.com/beatmaker/popular-tracks") == "https://soundcloud.com/beatmaker"


def test_is_soundcloud_link():
    assert is_soundcloud_link("https://soundcloud.com/user/track-name")
    assert is_soundcloud_link("вот мой бит soundcloud.com/beatmaker/fire-beat забери")
    assert is_soundcloud_link("https://on.soundcloud.com/AbCdEf")
    assert is_soundcloud_link("https://m.soundcloud.com/user/sets/beats")
    assert not is_soundcloud_link("https://youtube.com/watch?v=abc")
    assert not is_soundcloud_link("просто текст")


def test_extract_soundcloud_url_adds_scheme():
    assert extract_soundcloud_url("soundcloud.com/user/track") == "https://soundcloud.com/user/track"
    assert extract_soundcloud_url("нет ссылки") is None


def test_collect_entries_single_track():
    info = {"url": None, "webpage_url": "https://soundcloud.com/u/track1", "title": "Fire Beat"}
    entries = collect_soundcloud_entries(info)
    assert len(entries) == 1
    assert entries[0].title == "Fire Beat"


def test_collect_entries_profile_dedups():
    info = {
        "entries": [
            {"url": "https://soundcloud.com/u/track1", "title": "Beat 1"},
            {"url": "https://soundcloud.com/u/track2", "title": "Beat 2"},
            {"url": "https://soundcloud.com/u/track1", "title": "Beat 1 dup"},
            {"url": "https://example.com/other", "title": "чужое"},
        ]
    }
    entries = collect_soundcloud_entries(info)
    assert [e.title for e in entries] == ["Beat 1", "Beat 2"]


async def test_add_source_dedup_and_reactivate(session):
    from app.services.soundcloud_sources import add_source, list_sources

    source, created = await add_source(session, "https://soundcloud.com/zvyaga/")
    assert created is True
    assert source.url == "https://soundcloud.com/zvyaga"  # хвостовой слэш срезан

    again, created_again = await add_source(session, "https://soundcloud.com/zvyaga")
    assert created_again is False
    assert again.id == source.id

    source.status = "disabled"
    await session.commit()
    revived, _ = await add_source(session, "https://soundcloud.com/zvyaga")
    assert revived.status == "active"
    assert len(await list_sources(session)) == 1


async def test_sources_due_for_check(session):
    from datetime import timedelta

    from app.services.soundcloud_sources import (
        _utcnow,
        add_source,
        mark_checked,
        sources_due_for_check,
    )

    never_checked, _ = await add_source(session, "https://soundcloud.com/a")
    fresh, _ = await add_source(session, "https://soundcloud.com/b")
    stale, _ = await add_source(session, "https://soundcloud.com/c")
    disabled, _ = await add_source(session, "https://soundcloud.com/d")

    await mark_checked(session, fresh.id, found=5, imported=2)
    stale.last_checked_at = _utcnow() - timedelta(days=3)
    disabled.status = "disabled"
    disabled.last_checked_at = None
    await session.commit()

    due = await sources_due_for_check(session)

    assert never_checked.id in due
    assert stale.id in due
    assert fresh.id not in due
    assert disabled.id not in due
    await session.refresh(fresh)
    assert fresh.found_count == 5
    assert fresh.imported_count == 2
