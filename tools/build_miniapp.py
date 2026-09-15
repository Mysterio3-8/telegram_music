"""Сборка Mini App в один файл (16.09).

    python tools/build_miniapp.py            # собрать miniapp/app.bundle.js
    python tools/build_miniapp.py --check    # только проверить, что сборка свежая

Зачем: модули едут браузеру по одному, и он узнаёт о зависимости, только прочитав
того, кто её импортирует — 47 запросов в три круга ожидания. Один файл — один
запрос. Замер 16.08 показал, что на этом теряются секунды, и modulepreload пяти
модулей лечил лишь первый круг.

Сборщика уровня rollup здесь нет намеренно: на машине нет Node, а на сервере
деплой — это `git pull`, то есть собранный файл обязан лежать в репозитории.
Поэтому сборка простая и проверяемая:

- в коде Mini App только именованные импорты и экспорты (ни `export default`,
  ни `import * as`, ни динамического `import()` — проверено grep и тестом);
- каждый модуль оборачивается в функцию и возвращает свои экспорты, поэтому
  одноимённые локальные помощники в разных экранах не сталкиваются;
- порядок — топологический, цикл импортов это ошибка сборки, а не молчаливое
  `undefined` в рантайме;
- в заголовок пишется отпечаток исходников, и тест
  `tests/test_miniapp_bundle.py` валит сборку, если файл отстал от `src/`.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "miniapp"
SRC = ROOT / "src"
ENTRY = SRC / "main.js"
BUNDLE = ROOT / "app.bundle.js"

IMPORT_NAMED = re.compile(r"^import\s*\{([\s\S]*?)\}\s*from\s*[\"']([^\"']+)[\"'];?\s*$", re.MULTILINE)
IMPORT_BARE = re.compile(r"^import\s+[\"']([^\"']+)[\"'];?\s*$", re.MULTILINE)
EXPORT_DECL = re.compile(r"^export\s+(async\s+function|function|const|let|var|class)\s+([A-Za-z0-9_$]+)", re.MULTILINE)
FORBIDDEN = re.compile(r"^\s*(export\s+default|export\s*\{|export\s*\*|import\s*\*\s+as)", re.MULTILINE)


class BundleError(RuntimeError):
    pass


def module_id(path: Path) -> str:
    return path.relative_to(SRC).as_posix()


def parse(path: Path) -> dict:
    source = path.read_text(encoding="utf-8")
    if FORBIDDEN.search(source):
        raise BundleError(f"{module_id(path)}: сборщик не понимает default/namespace/re-export")
    deps: list[tuple[str, list[str]]] = []
    for names, target in IMPORT_NAMED.findall(source):
        resolved = (path.parent / target).resolve()
        if not resolved.is_file():
            raise BundleError(f"{module_id(path)}: не найден импорт {target}")
        imported = [n.strip() for n in names.split(",") if n.strip()]
        for name in imported:
            if " as " in name:
                raise BundleError(f"{module_id(path)}: переименование импорта не поддержано ({name})")
        deps.append((module_id(resolved), imported))
    for target in IMPORT_BARE.findall(source):
        resolved = (path.parent / target).resolve()
        deps.append((module_id(resolved), []))
    body = IMPORT_NAMED.sub("", source)
    body = IMPORT_BARE.sub("", body)
    body = EXPORT_DECL.sub(lambda m: f"{m.group(1)} {m.group(2)}", body)
    exports = [name for _kind, name in EXPORT_DECL.findall(source)]
    return {"id": module_id(path), "path": path, "deps": deps, "body": body.strip(), "exports": exports}


def collect() -> dict[str, dict]:
    modules: dict[str, dict] = {}
    queue = [ENTRY]
    while queue:
        path = queue.pop()
        mid = module_id(path)
        if mid in modules:
            continue
        module = parse(path)
        modules[mid] = module
        for dep_id, _names in module["deps"]:
            queue.append(SRC / dep_id)
    return modules


def order(modules: dict[str, dict]) -> list[str]:
    """Топологический порядок; цикл импортов — ошибка сборки."""
    result: list[str] = []
    state: dict[str, int] = {}

    def visit(mid: str, stack: list[str]) -> None:
        if state.get(mid) == 2:
            return
        if state.get(mid) == 1:
            raise BundleError("цикл импортов: " + " → ".join(stack + [mid]))
        state[mid] = 1
        for dep_id, _names in modules[mid]["deps"]:
            visit(dep_id, stack + [mid])
        state[mid] = 2
        result.append(mid)

    visit(module_id(ENTRY), [])
    return result


def fingerprint(modules: dict[str, dict]) -> str:
    digest = hashlib.sha256()
    for mid in sorted(modules):
        digest.update(mid.encode("utf-8"))
        digest.update(modules[mid]["path"].read_bytes())
    return digest.hexdigest()[:16]


def render(modules: dict[str, dict]) -> str:
    parts = [
        "// СОБРАНО АВТОМАТИЧЕСКИ — не править руками.",
        "// Источник: miniapp/src/**. Пересборка: python tools/build_miniapp.py",
        f"// отпечаток исходников: {fingerprint(modules)}",
        '(function () {\n  "use strict";\n  const __m = {};',
    ]
    for mid in order(modules):
        module = modules[mid]
        lines = [f'  __m["{mid}"] = (function () {{']
        for dep_id, names in module["deps"]:
            if names:
                lines.append(f'    const {{ {", ".join(names)} }} = __m["{dep_id}"];')
        lines.append("\n".join("    " + line if line else "" for line in module["body"].splitlines()))
        exported = ", ".join(module["exports"])
        lines.append(f"    return {{ {exported} }};")
        lines.append("  })();")
        parts.append("\n".join(lines))
    parts.append("})();")
    return "\n\n".join(parts) + "\n"


def build(check: bool) -> int:
    modules = collect()
    content = render(modules)
    if check:
        if not BUNDLE.is_file():
            print("Сборка отсутствует: python tools/build_miniapp.py")
            return 1
        if BUNDLE.read_text(encoding="utf-8") != content:
            print("Сборка отстала от miniapp/src: python tools/build_miniapp.py")
            return 1
        print(f"Сборка свежая: {len(modules)} модулей, {BUNDLE.stat().st_size // 1024} КБ")
        return 0
    BUNDLE.write_text(content, encoding="utf-8")
    print(f"Собрано модулей: {len(modules)}, файл {BUNDLE.name}, {len(content) // 1024} КБ")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    try:
        sys.exit(build(parser.parse_args().check))
    except BundleError as error:
        print(f"Сборка не удалась: {error}")
        sys.exit(2)


if __name__ == "__main__":
    main()
