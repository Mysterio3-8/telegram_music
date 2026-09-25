"""Замена DRM-трека должна быть той же записью (прогон 25.09, альбом Pop Smoke)."""
import pytest

from app.services.track_lookup.importer import is_same_recording
from app.services.track_lookup.ranking import Candidate, version_penalty


def _c(title, artist="Pop Smoke", duration=200, source="soundcloud"):
    return Candidate(source=source, url=f"https://x/{title}", title=title, duration=duration, artist=artist)


ORIGINAL = _c("Diana (feat. King Combs)", duration=210)
QUERY = "Pop Smoke Diana (feat. King Combs)"


@pytest.mark.parametrize(
    "alternative",
    [
        _c("Diana Ft. King Combs(Fast)", duration=163),
        _c("Diana Ft. King Combs(Fast)", duration=210),  # пометка ловится и без длительности
        _c("Diana (Slowed + Reverb)", duration=250),
        _c("Diana (Ertuğ Y. Remix)", duration=212),
        _c("Diana [Piano Cover]", duration=208),
        _c("Diana Type Beat", artist="Jamar", duration=205),
        _c("Gangstas", duration=210),  # другой трек того же артиста
    ],
)
def test_other_recordings_rejected(alternative):
    assert not is_same_recording(ORIGINAL, QUERY, alternative)


@pytest.mark.parametrize(
    "alternative",
    [
        _c("Diana (feat. King Combs)", duration=211),
        _c("Diana", duration=206, source="youtube"),
        _c("Diana ft. King Combs", artist="*RIP Pop Smoke*", duration=0),
    ],
)
def test_same_recording_accepted(alternative):
    assert is_same_recording(ORIGINAL, QUERY, alternative)


def test_asked_for_version_is_not_penalised():
    original = _c("Diana (Fast)", duration=160)
    assert is_same_recording(original, "Pop Smoke Diana (Fast)", _c("Diana (fast)", duration=161))


def test_speed_tag_only_in_brackets():
    assert version_penalty("fast car", "Tracy Chapman Fast Car") == 1.0
    assert version_penalty("tunnel vision", "Tunnel Vision (Outro)(Fast)") < 1.0
    assert version_penalty("пачка", "Пачка (ускоренная версия)") < 1.0
