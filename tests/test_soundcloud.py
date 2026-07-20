from app.services.soundcloud import (
    collect_soundcloud_entries,
    extract_soundcloud_url,
    is_soundcloud_link,
    normalize_soundcloud_url,
)


def test_normalize_collapses_only_broken_tabs():
    # /popular-tracks у yt-dlp даёт 404 → сворачиваем к корню профиля
    assert normalize_soundcloud_url("https://soundcloud.com/ilya-sokruta/popular-tracks") == "https://soundcloud.com/ilya-sokruta"
    assert normalize_soundcloud_url("https://soundcloud.com/user/popular-tracks?x=1") == "https://soundcloud.com/user"


def test_normalize_keeps_valid_pages():
    # yt-dlp открывает эти страницы напрямую — «скачать лайки» должно качать лайки
    assert normalize_soundcloud_url("https://soundcloud.com/user/tracks") == "https://soundcloud.com/user/tracks"
    assert normalize_soundcloud_url("https://soundcloud.com/user/likes/") == "https://soundcloud.com/user/likes"
    assert normalize_soundcloud_url("https://soundcloud.com/user/reposts") == "https://soundcloud.com/user/reposts"
    assert normalize_soundcloud_url("https://soundcloud.com/user/my-beat") == "https://soundcloud.com/user/my-beat"
    assert normalize_soundcloud_url("https://soundcloud.com/user/sets/my-pack") == "https://soundcloud.com/user/sets/my-pack"
    assert normalize_soundcloud_url("https://soundcloud.com/user") == "https://soundcloud.com/user"


def test_normalize_search_and_tags_to_scsearch():
    # Страницы поиска/тега не имеют API-URL → переводим в scsearch
    assert normalize_soundcloud_url("https://soundcloud.com/search?q=phonk").startswith("scsearch")
    assert normalize_soundcloud_url("https://soundcloud.com/search?q=phonk").endswith(":phonk")
    assert normalize_soundcloud_url("https://soundcloud.com/search/sounds?q=dark%20trap").endswith(":dark trap")
    assert normalize_soundcloud_url("https://soundcloud.com/tags/lo-fi").endswith(":lo fi")
    # идемпотентность: уже нормализованный запрос не ломается
    assert normalize_soundcloud_url("scsearch200:phonk") == "scsearch200:phonk"


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


async def test_import_skips_known_urls(session, monkeypatch):
    """Инкрементальный скан: уже обработанные ссылки не качаются повторно (анти-бан)."""
    from app.db.models import SoundcloudImported
    from app.services import soundcloud_import as si
    from app.services.soundcloud import SoundcloudEntry
    from app.services.youtube.downloader import DownloadedAudio

    session.add(SoundcloudImported(url="https://soundcloud.com/u/old"))
    await session.commit()

    monkeypatch.setattr(
        si,
        "list_soundcloud_entries",
        lambda url: [
            SoundcloudEntry("https://soundcloud.com/u/old", "Old"),
            SoundcloudEntry("https://soundcloud.com/u/new", "New"),
        ],
    )
    downloaded = []

    def fake_dl(url):
        downloaded.append(url)
        return DownloadedAudio(data=b"x" * 1000, file_format="mp3", duration=120, video_title="New"), "Uploader"

    monkeypatch.setattr(si, "download_soundcloud_audio", fake_dl)
    monkeypatch.setattr(si, "compute_fingerprint_from_bytes", lambda *a, **k: "fp-new")

    class FakeBot:
        async def send_audio(self, *a, **k):
            class M:
                class audio:
                    file_id = "f1"
            return M()

    report = await si.import_soundcloud_tracks(session, FakeBot(), "https://soundcloud.com/u")

    assert downloaded == ["https://soundcloud.com/u/new"]  # старую не качали
    assert report.skipped_known == 1
    assert report.imported == 1
    # новая теперь помечена — второй скан её пропустит
    assert await si._already_seen(session, "https://soundcloud.com/u/new") is True


async def test_permanent_failures_marked_seen_transient_are_not(session, monkeypatch):
    """DRM/приватные треки не ретраятся вечно; сетевые ошибки — ретраятся."""
    from app.services import soundcloud_import as si
    from app.services.soundcloud import SoundcloudEntry

    monkeypatch.setattr(
        si,
        "list_soundcloud_entries",
        lambda url: [
            SoundcloudEntry("https://soundcloud.com/u/drm-track", "DRM"),
            SoundcloudEntry("https://soundcloud.com/u/flaky-track", "Flaky"),
        ],
    )

    def fake_dl(url):
        if "drm" in url:
            raise RuntimeError("ERROR: [soundcloud] xxx: This video is DRM protected")
        raise RuntimeError("HTTP Error 502: Bad Gateway")

    monkeypatch.setattr(si, "download_soundcloud_audio", fake_dl)

    class FakeBot:
        pass

    report = await si.import_soundcloud_tracks(session, FakeBot(), "https://soundcloud.com/u")

    assert report.failed == 2
    assert await si._already_seen(session, "https://soundcloud.com/u/drm-track") is True
    assert await si._already_seen(session, "https://soundcloud.com/u/flaky-track") is False


def test_soundcloud_link_kind():
    from app.services.soundcloud import soundcloud_link_kind

    # одиночный трек — бесплатно
    assert soundcloud_link_kind("https://soundcloud.com/user/my-beat") == "track"
    # профиль / разделы / поиск — пачка (Premium)
    assert soundcloud_link_kind("https://soundcloud.com/user") == "bulk"
    assert soundcloud_link_kind("https://soundcloud.com/user/likes") == "bulk"
    assert soundcloud_link_kind("https://soundcloud.com/user/tracks") == "bulk"
    assert soundcloud_link_kind("https://soundcloud.com/user/sets/my-pack") == "bulk"
    assert soundcloud_link_kind("https://soundcloud.com/search?q=phonk") == "bulk"
    assert soundcloud_link_kind("https://soundcloud.com/tags/lofi") == "bulk"
    # не SoundCloud
    assert soundcloud_link_kind("https://youtube.com/watch?v=abc") is None
