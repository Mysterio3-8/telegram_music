from app.storage.local import LocalStorage


def test_local_storage_roundtrip(tmp_path):
    storage = LocalStorage(str(tmp_path))

    path = storage.save("tracks/1", b"audio-bytes")

    assert path == "local://tracks/1"
    assert storage.exists("tracks/1")
    assert storage.load("tracks/1") == b"audio-bytes"


def test_local_storage_missing_key(tmp_path):
    storage = LocalStorage(str(tmp_path))

    assert storage.exists("tracks/404") is False


def test_local_storage_creates_nested_dirs(tmp_path):
    storage = LocalStorage(str(tmp_path))

    storage.save("a/b/c/file", b"x")

    assert (tmp_path / "a" / "b" / "c" / "file").read_bytes() == b"x"
