"""Мягкий нагрузочный тест прода (окно владельца 03:00–05:00 МСК, без рассылки).

    python scripts/load_test_prod.py --token <JWT> --stages 5:30,20:30,50:30

Ступени «одновременных клиентов : секунд». Между ступенями пауза — сервер должен
успеть выдохнуть. Тест САМ останавливается, если пошли ошибки: это прод на одном
ядре и 961 МБ, и ронять его ради замера нельзя.

⚠️ Латентность меряется с машины владельца, то есть включает интернет до сервера;
сравнивать имеет смысл ступени между собой, а не с локальным прогоном.
"""
import argparse
import asyncio
import statistics
import time

import aiohttp

# Что дёргаем: страница каталога, id библиотеки, полки главной, статика Mini App.
# Веса — грубая имитация живого открытия приложения.
ENDPOINTS = [
    ("/api/tracks?page=1&page_size=5", True, 3),
    ("/api/library/ids", True, 2),
    ("/api/shelves", True, 2),
    ("/src/main.js", False, 1),
]

ABORT_ERROR_PCT = 2.0
ABORT_P95_SEC = 5.0


class Stage:
    def __init__(self, workers: int, seconds: int) -> None:
        self.workers, self.seconds = workers, seconds
        self.latency: list[float] = []
        self.codes: dict[int, int] = {}
        self.failures = 0

    @property
    def errors_pct(self) -> float:
        bad = self.failures + sum(n for code, n in self.codes.items() if code >= 500)
        total = len(self.latency) + self.failures
        return bad * 100 / total if total else 0.0

    def p(self, q: float) -> float:
        if not self.latency:
            return 0.0
        ordered = sorted(self.latency)
        return ordered[min(len(ordered) - 1, int(len(ordered) * q))]


async def _worker(session, base, token, stage, deadline, plan):
    headers = {"Authorization": f"Bearer {token}"}
    index = 0
    while time.monotonic() < deadline:
        path, needs_auth, _ = plan[index % len(plan)]
        index += 1
        started = time.monotonic()
        try:
            async with session.get(
                base + path, headers=headers if needs_auth else {}, timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                await response.read()
                stage.codes[response.status] = stage.codes.get(response.status, 0) + 1
                stage.latency.append(time.monotonic() - started)
        except Exception:  # noqa: BLE001 — обрыв тоже результат замера
            stage.failures += 1


async def run(base: str, token: str, stages: list[tuple[int, int]]) -> int:
    plan = [item for item in ENDPOINTS for _ in range(item[2])]
    async with aiohttp.ClientSession() as session:
        for workers, seconds in stages:
            stage = Stage(workers, seconds)
            deadline = time.monotonic() + seconds
            await asyncio.gather(
                *[_worker(session, base, token, stage, deadline, plan) for _ in range(workers)]
            )
            done = len(stage.latency)
            print(
                f"{workers:>3} клиентов / {seconds} сек: запросов {done}, "
                f"p50 {stage.p(0.5) * 1000:.0f} мс, p95 {stage.p(0.95) * 1000:.0f} мс, "
                f"max {max(stage.latency, default=0) * 1000:.0f} мс, "
                f"среднее {statistics.mean(stage.latency) * 1000:.0f} мс, "
                f"коды {dict(sorted(stage.codes.items()))}, обрывов {stage.failures}",
                flush=True,
            )
            if stage.errors_pct > ABORT_ERROR_PCT or stage.p(0.95) > ABORT_P95_SEC:
                print(f"СТОП: ошибок {stage.errors_pct:.1f}%, p95 {stage.p(0.95):.1f} сек — дальше не гружу")
                return 1
            await asyncio.sleep(10)  # пауза между ступенями
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="https://keybest.cc")
    parser.add_argument("--token", required=True)
    parser.add_argument("--stages", default="5:30,20:30,50:30")
    args = parser.parse_args()
    stages = [(int(w), int(s)) for w, s in (part.split(":") for part in args.stages.split(","))]
    raise SystemExit(asyncio.run(run(args.base.rstrip("/"), args.token, stages)))


if __name__ == "__main__":
    main()
