import json
import logging
import subprocess
import tempfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

FPCALC_TIMEOUT = 30


def compute_fingerprint(path: str) -> str | None:
    """Акустический отпечаток chromaprint через fpcalc. None, если fpcalc недоступен."""
    try:
        result = subprocess.run(
            [settings.fpcalc_path, "-json", path],
            capture_output=True,
            text=True,
            timeout=FPCALC_TIMEOUT,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning("fpcalc недоступен или упал: %s", exc)
        return None

    fingerprint = json.loads(result.stdout).get("fingerprint")
    return fingerprint or None


def compute_fingerprint_from_bytes(data: bytes, suffix: str = ".audio") -> str | None:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        return compute_fingerprint(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
