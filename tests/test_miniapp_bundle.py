"""Сборка Mini App в один файл (16.09).

Файл `miniapp/app.bundle.js` лежит в репозитории, потому что деплой на сервере —
это `git pull` без сборки. Значит, отстать он может молча: правку в `src/`
никто не увидит на проде. Этот тест — сторож.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_miniapp  # noqa: E402


def test_bundle_matches_sources():
    modules = build_miniapp.collect()
    expected = build_miniapp.render(modules)
    actual = build_miniapp.BUNDLE.read_text(encoding="utf-8")
    assert actual == expected, "Сборка отстала: python tools/build_miniapp.py"


def test_every_module_reached_and_no_cycles():
    modules = build_miniapp.collect()
    on_disk = {p.relative_to(build_miniapp.SRC).as_posix() for p in build_miniapp.SRC.rglob("*.js")}
    # Модуль, который никто не импортирует, в сборку не попадёт — значит, он мёртв
    assert on_disk - set(modules) == set(), "модули не попали в сборку (мёртвый код?)"
    build_miniapp.order(modules)  # цикл импортов бросил бы BundleError


def test_index_html_loads_bundle_not_modules():
    html = (ROOT / "miniapp" / "index.html").read_text(encoding="utf-8")
    assert "/app.bundle.js" in html
    assert 'src="/src/main.js"' not in html


def test_bundle_keeps_module_scope():
    """Каждый модуль — своя область видимости: одноимённые помощники не сталкиваются."""
    bundle = build_miniapp.BUNDLE.read_text(encoding="utf-8")
    assert bundle.count("__m[") >= 47
    assert "export " not in bundle and "import " not in bundle
