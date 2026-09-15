"""Домен Mini App не зашит в код (15.09, подготовка переезда с keybest.cc).

Предупреждение Safari «Deceptive Website Warning» живёт на домене — лечение
переездом. Правка файлов репозитория на сервере невозможна (автодеплой делает
`git reset --hard`), поэтому всё доменное должно браться из nginx и .env
(`PUBLIC_BASE_URL`), а в коде и статике Mini App домена быть не должно.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "keybest"


def _offenders(paths) -> list[str]:
    found = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0] if path.suffix == ".py" else line
            if DOMAIN in code:
                found.append(f"{path.relative_to(ROOT)}:{number}")
    return found


def test_miniapp_has_no_hardcoded_domain():
    files = [p for p in (ROOT / "miniapp").rglob("*") if p.suffix in {".js", ".html", ".css", ".txt", ".json"}]
    assert files, "Mini App не найден"
    assert _offenders(files) == []


def test_app_code_has_no_hardcoded_domain():
    files = list((ROOT / "app").rglob("*.py"))
    assert _offenders(files) == []
