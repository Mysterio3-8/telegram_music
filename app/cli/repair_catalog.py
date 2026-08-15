"""Пакетное восстановление каталога после переезда на нового бота.

    python -m app.cli.repair_catalog                 # показать масштаб, ничего не делать
    python -m app.cli.repair_catalog --apply --limit 200
    python -m app.cli.repair_catalog --apply --limit 50 --popular

🔴 Зачем. `tg_file_id` принадлежит боту, который загрузил файл. После переезда на
@muz_damn_bot (05.08) идентификаторы всего старого каталога стали чужими. Замер
15.08: **7223 трека из 7491 — 96%** — с мёртвым id, живых 262, архивных копий
ноль. Бот такой трек лечит при обращении, а Mini App до 15.08 просто отдавал 404
и бесконечно пропускал.

Лечение по обращению работает, но чинит только то, что кто-то нажал. Эта команда
чинит впрок, порциями, чтобы каталог ожил не через год, а за месяц.

⚠️ **Почему порциями, а не всё сразу.** Восстановление одного трека — это поиск
в источнике, скачивание и отправка в Telegram: около 8 секунд и заметный кусок
единственного ядра. Плюс Telegram не даёт боту слать в один чат быстрее ~15
файлов в минуту. Всё разом это 16 часов работы, за которые машина ляжет: 15.08
массовый прогон скачиваний дважды уронил sshd на этом же боксе.

Разумный режим — 200 треков в сутки в ежедневном таймере: около получаса работы,
и весь каталог оживает за пять недель.
"""
import argparse
import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from sqlalchemy import func, select

from app.config import settings
from app.db.base import session_factory
from app.db.models import Track, TrackEvent

logger = logging.getLogger(__name__)

# Пауза между треками. Telegram не даст боту быстрее ~15 файлов в минуту в один
# чат, а упереться в его лимит — значит получить 429 и остановку всей пачки.
PAUSE_SECONDS = 4.0

# Дата переезда на @muz_damn_bot. Всё, что заведено раньше, минтил СТАРЫЙ бот,
# и его идентификаторы нынешнему не принадлежат.
BOT_SWAP = datetime(2026, 8, 5)


async def _summary(session) -> None:
    """Показывает масштаб: сколько треков заведомо мертво, сколько живо."""
    total = await session.scalar(select(func.count()).select_from(Track)) or 0
    suspect = await session.scalar(
        select(func.count()).select_from(Track).where(
            Track.tg_file_id.is_not(None), Track.created_at < BOT_SWAP
        )
    ) or 0
    alive = await session.scalar(
        select(func.count()).select_from(Track).where(
            Track.tg_file_id.is_not(None), Track.created_at >= BOT_SWAP
        )
    ) or 0
    waiting = await session.scalar(
        select(func.count()).select_from(Track).where(Track.tg_file_id.is_(None))
    ) or 0
    print(f"всего треков:                 {total}")
    print(f"минтил старый бот (мертвы):   {suspect}")
    print(f"минтил нынешний бот (живы):   {alive}")
    print(f"id уже погашен, ждут ремонта: {waiting}")


async def _is_dead(bot: Bot, file_id: str) -> bool:
    """Мёртв ли идентификатор. Проверяем `get_file` — он спрашивает Telegram о
    файле, но НЕ качает его: килобайты трафика вместо мегабайтов.

    Без этой проверки пришлось бы либо гадать по дате, либо перекачивать
    вслепую. Первое ошибается, второе стоит восемь секунд на каждый зря
    тронутый трек.
    """
    from aiogram.exceptions import TelegramBadRequest

    try:
        await bot.get_file(file_id)
        return False
    except TelegramBadRequest:
        return True
    except Exception:  # noqa: BLE001 — сеть моргнула: считаем живым, тронем позже
        return False


async def _pick(session, limit: int, popular: bool) -> list[Track]:
    """Кандидаты на восстановление.

    Берём и тех, у кого id уже погашен (мёртв наверняка), и тех, кто заведён до
    переезда на нового бота — у этих id чужой по построению. Живость каждого
    проверяем `get_file` перед тем, как качать заново.

    popular=True — сперва те, которые люди действительно слушают: чинить в
    первую очередь мёртвый груз незачем.
    """
    stmt = select(Track).where(
        (Track.tg_file_id.is_(None)) | (Track.created_at < BOT_SWAP)
    )
    if popular:
        plays = (
            select(TrackEvent.track_id, func.count().label("n"))
            .group_by(TrackEvent.track_id)
            .subquery()
        )
        stmt = stmt.outerjoin(plays, plays.c.track_id == Track.id).order_by(
            func.coalesce(plays.c.n, 0).desc(), Track.id
        )
    return list((await session.scalars(stmt.limit(limit))).all())


async def run(limit: int, apply: bool, popular: bool) -> int:
    from app.services.track_repair import repair_track_file_id

    async with session_factory() as session:
        await _summary(session)
        targets = await _pick(session, limit, popular)

    if not targets:
        print("\nВосстанавливать нечего. Мёртвые id гасятся при обращении —")
        print("сыграйте трек в боте или Mini App, и он попадёт сюда.")
        return 0

    print(f"\nВ этот заход: {len(targets)}")
    if not apply:
        for track in targets[:10]:
            print(f"  {track.id}: {track.artist} — {track.title}")
        if len(targets) > 10:
            print(f"  … и ещё {len(targets) - 10}")
        print("\nЭто пробный прогон. Чтобы чинить — повторите с --apply")
        return 0

    healed = failed = skipped = 0
    bot = Bot(token=settings.bot_token)
    try:
        for number, track in enumerate(targets, start=1):
            async with session_factory() as session:
                fresh = await session.get(Track, track.id)
                if fresh is None:
                    continue
                # Идентификатор ещё жив — трогать нечего. Так отсеиваются 262
                # трека, заминченные уже новым ботом, и всё, что вылечилось само.
                if fresh.tg_file_id and not await _is_dead(bot, fresh.tg_file_id):
                    skipped += 1
                    continue
                fresh.tg_file_id = None
                fresh.meta_synced = False
                await session.commit()
                try:
                    ok = await repair_track_file_id(session, bot, fresh)
                except Exception:  # noqa: BLE001 — один трек не должен ронять пачку
                    logger.warning("Восстановление track=%s упало", track.id, exc_info=True)
                    ok = False
            healed += int(ok)
            failed += int(not ok)
            print(f"  [{number}/{len(targets)}] {'✅' if ok else '❌'} {track.artist} — {track.title}")
            await asyncio.sleep(PAUSE_SECONDS)
    finally:
        await bot.session.close()

    print(
        f"\nВосстановлено: {healed}, не нашлось в источниках: {failed}, "
        f"id оказался жив: {skipped}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Восстановление file_id каталога порциями")
    parser.add_argument("--limit", type=int, default=50, help="сколько треков за прогон")
    parser.add_argument("--apply", action="store_true", help="чинить, а не только показывать")
    parser.add_argument(
        "--popular", action="store_true", help="начать с тех, что реально слушают"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    return asyncio.run(run(args.limit, args.apply, args.popular))


if __name__ == "__main__":
    raise SystemExit(main())
