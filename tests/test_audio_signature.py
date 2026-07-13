from urllib.parse import parse_qs, urlparse

from app.api.security import build_audio_url, verify_audio_signature


def _parse(url: str) -> tuple[int, int, str]:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    track_id = int(parsed.path.split("/")[2])
    return track_id, int(params["exp"][0]), params["sig"][0]


def test_build_audio_url_signature_verifies():
    track_id, exp, sig = _parse(build_audio_url(42))

    assert track_id == 42
    assert verify_audio_signature(42, exp, sig) is True


def test_signature_rejects_other_track():
    _, exp, sig = _parse(build_audio_url(42))

    assert verify_audio_signature(43, exp, sig) is False


def test_signature_rejects_tampered_expiry():
    _, exp, sig = _parse(build_audio_url(42))

    assert verify_audio_signature(42, exp + 9999, sig) is False


def test_signature_rejects_expired():
    _, exp, sig = _parse(build_audio_url(42))
    import app.api.security as security

    expired = exp - security.AUDIO_URL_TTL_SECONDS - 10
    assert verify_audio_signature(42, expired, sig) is False
