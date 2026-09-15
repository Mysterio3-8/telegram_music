"""Вердикт тестов для автодеплоя: на прод едет только коммит с зелёными тестами."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "ci_verdict.py"
_spec = importlib.util.spec_from_file_location("ci_verdict", SCRIPT)
ci_verdict = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci_verdict)


def _run(status: str, conclusion: str | None, app: str = "github-actions") -> dict:
    return {"status": status, "conclusion": conclusion, "app": {"slug": app}}


def test_green_run_is_success():
    assert ci_verdict.verdict({"check_runs": [_run("completed", "success")]}) == "success"


def test_rerun_after_red_counts_as_success():
    runs = [_run("completed", "failure"), _run("completed", "success")]
    assert ci_verdict.verdict({"check_runs": runs}) == "success"


def test_red_run_is_failure():
    assert ci_verdict.verdict({"check_runs": [_run("completed", "failure")]}) == "failure"


def test_no_runs_yet_is_pending():
    assert ci_verdict.verdict({"check_runs": []}) == "pending"
    assert ci_verdict.verdict({}) == "pending"


def test_running_is_pending_not_failure():
    runs = [_run("completed", "cancelled"), _run("in_progress", None)]
    assert ci_verdict.verdict({"check_runs": runs}) == "pending"


def test_foreign_app_success_is_ignored():
    """Чужое приложение с checks:write не может разрешить выкатку."""
    runs = [_run("completed", "success", app="some-bot")]
    assert ci_verdict.verdict({"check_runs": runs}) == "pending"


def test_cli_survives_garbage():
    for stdin in ("not json", "[]", json.dumps({"check_runs": [_run("completed", "success")]})):
        out = subprocess.run(
            [sys.executable, str(SCRIPT)], input=stdin, capture_output=True, text=True, check=True
        ).stdout.strip()
        assert out in {"pending", "success"}
    assert out == "success"
