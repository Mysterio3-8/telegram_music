"""Замер качества выдачи на размеченных запросах.

Зачем отдельный инструмент. Веса ранжирования (`_ARTIST_BONUS`, `_TITLE_BONUS`,
доля популярности) подбирались прогоном по живым запросам — но сам прогон жил в
черновике и до репозитория не доехал. Следующая сессия, меняя любую из этих
цифр, чинила одно и вслепую ломала другое. Здесь он зафиксирован.

Проверяем ПЕРВУЮ строку выдачи: именно её человек слышит, всё остальное он
листает. Ожидание — исполнитель, а не название: у половины спорных запросов
песни не существует вовсе (замер 16.08: «нурминский вечно молодой» и
«литвиненко эйфория» не находятся ни на SoundCloud, ни на YouTube), и требовать
точного названия значило бы требовать невозможного. Где название всё же обязано
совпасть, оно указано вторым полем.

    python -m app.cli.search_bench                  # весь набор
    python -m app.cli.search_bench --only тейп      # один запрос, подробно

⚠️ Это ПОИСК, без скачивания: на одноядерном боксе безопасно (см.
docs/tasks/2026-08-15-контекст-новой-сессии.md — пачечные скачивания роняют sshd).
"""
import argparse
import asyncio
import time

from app.services.track_lookup import search_candidates
from app.services.track_lookup.ranking import (
    Candidate,
    match_score,
    normalize_query,
    phonetic,
)

# (запрос, ожидаемый исполнитель, ожидаемое название или None)
#
# Набор — не выдумка, а живые жалобы и разборы: каждая строка когда-то выдавала
# не то, и почти каждая описана в CLAUDE.md или в docs/tasks/.
CASES: list[tuple[str, str, str | None]] = [
    # Кириллица: основной репертуар, SoundCloud
    ("кизару фейк айди", "kizaru", "fake id"),
    ("мияги ямакаси", "miyagi", "yamakasi"),
    ("три дня дождя дышать", "три дня дождя", "всю ночь тобой дышать"),
    ("элджей розовое вино", "элджей", "розовое вино"),
    ("скриптонит вечеринка", "скриптонит", None),
    ("хаски панелька", "хаски", "панелька"),
    ("макан пополам", "macan", None),
    ("нурминский валим", "нурминский", "валим"),
    ("буда", "og buda", None),
    ("кизару", "kizaru", None),
    ("платина", "платина", None),
    ("тейп", "big baby tape", None),
    # Артист есть, песни нет ни в одном источнике — ждём хотя бы верного артиста
    ("макан назови её", "macan", None),
    ("нурминский вечно молодой", "нурминский", None),
    ("литвиненко эйфория", "литвиненко", None),
    # Латиница: западный репертуар, YouTube несёт основную нагрузку
    ("eminem lose yourself", "eminem", "lose yourself"),
    ("daft punk one more time", "daft punk", "one more time"),
    ("kendrick lamar humble", "kendrick lamar", None),
    ("the weeknd blinding lights", "the weeknd", "blinding lights"),
    ("big baby tape nobody", "big baby tape", "nobody"),
]


def _looks_like(expected: str, actual: str) -> bool:
    """Совпадение «на слух»: артист пишется как угодно («макан» ↔ «MACAN»).

    ⚠️ Проверка НАПРАВЛЕННАЯ: ожидаемое должно найтись в полученном, но не
    наоборот. Симметричная версия, с которой я начал, засчитывала ровно тот
    промах, ради которого затевался замер: по «тейп» приходит турецкая группа
    «Teyp», её фонетическая форма «tap» — подстрока от «big baby tap», и прогон
    рапортовал 20 из 20. Совпадение части имени с целым именем совпадением не
    является; фиты вроде «Aarne, Toxi$, Big Baby Tape» проходят и так — там
    ожидаемое целиком лежит внутри полученного.
    """
    if not actual:
        return False
    want = phonetic(normalize_query(expected))
    got = phonetic(normalize_query(actual))
    return bool(want) and want in got


def _verdict(case: tuple[str, str, str | None], top: Candidate | None) -> tuple[bool, str]:
    _, want_artist, want_title = case
    if top is None:
        return False, "пусто"
    if not _looks_like(want_artist, top.artist or ""):
        return False, f"чужой исполнитель: {top.artist}"
    if want_title and not _looks_like(want_title, top.title or ""):
        return False, f"не та песня: {top.title}"
    return True, "ок"


async def run(cases: list[tuple[str, str, str | None]], verbose: bool) -> int:
    good = 0
    started = time.perf_counter()
    for case in cases:
        query = case[0]
        began = time.perf_counter()
        candidates = await search_candidates(query)
        spent = time.perf_counter() - began
        top = candidates[0] if candidates else None
        passed, note = _verdict(case, top)
        good += passed
        mark = "OK  " if passed else "МИМО"
        first = f"{top.artist} — {top.title}" if top else "—"
        print(f"{mark} {spent:5.2f}с  «{query}» -> {first}    [{note}]")
        if verbose:
            for item in candidates[:8]:
                print(
                    f"        {match_score(query, item):.2f} "
                    f"pop={item.popularity} src={item.source} "
                    f"| {item.artist} — {item.title}"
                )
    total = len(cases)
    print(
        f"\nИтог: {good} из {total} "
        f"({good * 100 // max(1, total)}%), всего {time.perf_counter() - started:.0f} сек"
    )
    return good


def main() -> None:
    parser = argparse.ArgumentParser(description="Качество выдачи на размеченных запросах")
    parser.add_argument("--only", help="прогнать только запросы, содержащие эту подстроку")
    parser.add_argument("-v", "--verbose", action="store_true", help="показывать топ-8 по каждому")
    args = parser.parse_args()

    cases = [c for c in CASES if not args.only or args.only.lower() in c[0].lower()]
    if not cases:
        raise SystemExit("Под фильтр не попал ни один запрос")
    asyncio.run(run(cases, args.verbose))


if __name__ == "__main__":
    main()
