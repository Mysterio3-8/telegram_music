from app.services import fingerprint
from app.services.fingerprint import compute_fingerprint, compute_fingerprint_from_bytes


def test_returns_none_when_fpcalc_missing(monkeypatch):
    monkeypatch.setattr(fingerprint.settings, "fpcalc_path", "definitely-not-a-real-binary-xyz")

    assert compute_fingerprint("whatever.mp3") is None


def test_parses_fpcalc_json(monkeypatch):
    class FakeResult:
        stdout = '{"duration": 200, "fingerprint": "AQAAB_kZ"}'

    monkeypatch.setattr(fingerprint.subprocess, "run", lambda *a, **k: FakeResult())

    assert compute_fingerprint("track.mp3") == "AQAAB_kZ"


def test_from_bytes_cleans_up_temp(monkeypatch):
    captured = {}

    def fake_compute(path):
        captured["path"] = path
        return "FP123"

    monkeypatch.setattr(fingerprint, "compute_fingerprint", fake_compute)

    result = compute_fingerprint_from_bytes(b"data", suffix=".mp3")

    assert result == "FP123"
    import os

    assert not os.path.exists(captured["path"])  # временный файл удалён
