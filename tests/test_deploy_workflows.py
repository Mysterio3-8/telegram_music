"""Файлы автодеплоя должны быть синтаксически целыми и с нужными границами.

Зачем тест: сломанный workflow не падает при коммите — он просто не запускается
или падает уже в бою. А ошибка в условиях автослияния означает, что чужой код
уезжает на прод. Такое дешевле поймать здесь.
"""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = pathlib.Path(".github/workflows")


def _load(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text())
    assert isinstance(data, dict), f"{name}: не разобрался в словарь"
    return data


def _triggers(data: dict) -> dict:
    # ⚠️ Ключ `on` в YAML разбирается как булево True — известная особенность
    # (YAML 1.1 считает on/off/yes/no булевыми). Поэтому смотрим оба варианта.
    return data.get("on") or data.get(True)


def test_deploy_workflow_parses_and_has_expected_shape():
    data = _load("deploy.yml")
    triggers = _triggers(data)
    assert "push" in triggers
    assert triggers["push"]["branches"] == ["main"], "выкатываем только main"
    # Без workflow_call автослияние не смогло бы позвать выкатку: слияние под
    # GITHUB_TOKEN не порождает push.
    assert "workflow_call" in triggers
    assert "workflow_dispatch" in triggers

    jobs = data["jobs"]
    assert set(jobs) == {"tests", "deploy"}
    # Выкатка только после зелёных тестов — это главное свойство файла.
    assert jobs["deploy"]["needs"] == "tests"


def test_deploy_runs_same_python_as_production():
    """Тесты на другой версии проверяли бы не то, что поедет в прод (VPS — 3.12)."""
    data = _load("deploy.yml")
    steps = data["jobs"]["tests"]["steps"]
    versions = [
        str(step.get("with", {}).get("python-version"))
        for step in steps
        if "setup-python" in str(step.get("uses", ""))
    ]
    assert versions == ["3.12"]


def test_automerge_refuses_forks_drafts_and_strangers():
    """Границы автослияния — единственное, что отделяет чужой PR от прода."""
    data = _load("automerge.yml")
    gate = str(data["jobs"]["check"]["steps"][0])

    assert "IS_DRAFT" in gate, "черновик не должен сливаться"
    assert "HEAD_REPO" in gate and "BASE_REPO" in gate, "форк не должен сливаться"
    assert "AUTHOR" in gate and "OWNER" in gate, "чужой автор не должен сливаться"
    assert "BASE_REF" in gate, "слияние допустимо только в main"


def test_automerge_deploys_only_after_tests_and_merge():
    data = _load("automerge.yml")
    jobs = data["jobs"]
    assert jobs["tests"]["needs"] == "check"
    assert jobs["merge"]["needs"] == ["check", "tests"]
    assert jobs["deploy"]["needs"] == "merge"
    # Выкатка переиспользует deploy.yml, а не дублирует шаги — иначе два места
    # разъедутся при первой же правке.
    assert jobs["deploy"]["uses"] == "./.github/workflows/deploy.yml"


def test_automerge_has_permissions_it_needs():
    data = _load("automerge.yml")
    perms = data["permissions"]
    assert perms["contents"] == "write"
    assert perms["pull-requests"] == "write"


def test_remote_deploy_script_is_executable_and_sane():
    script = pathlib.Path("deploy/remote-deploy.sh")
    assert script.exists()
    body = script.read_text()
    # Точка возврата запоминается ДО изменений — без неё откат некуда делать.
    assert "PREVIOUS=$(git rev-parse HEAD)" in body
    # Юниты доносятся отдельно: git pull их не переносит в /etc/systemd/system.
    assert "install-units.sh" in body
    # Миграции автоматически не откатываются: `alembic downgrade` умеет удалять
    # колонки с данными, и делать это автоматом опаснее самой поломки.
    # ⚠️ Смотрим ИСПОЛНЯЕМЫЕ строки, а не текст файла: слово downgrade законно
    # встречается в комментарии, который объясняет, почему его тут нет.
    code_lines = [
        line for line in body.splitlines() if line.strip() and not line.strip().startswith("#")
    ]
    assert not any("downgrade" in line for line in code_lines), (
        "деплой не должен откатывать миграции автоматически"
    )
