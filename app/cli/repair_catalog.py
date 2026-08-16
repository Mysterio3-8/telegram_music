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
from datetime import datetime, timedelta

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

# Через сколько дней возвращаться к треку, которым уже занимались. Две недели:
# «не нашлось в источниках» — состояние временное (каталоги SoundCloud и YouTube
# пополняются), но пробовать каждую ночь одно и то же значит не чинить остальное.
RECHECK_AFTER_DAYS = 14


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
    # ⚠️ «Заведены до переезда», а не «мертвы»: восстановленный трек сохраняет
    # свой created_at, и отличить его от нетронутого по базе нельзя. Поэтому
    # число здесь не убывает по ходу ремонта — это счётчик подозрений, а не
    # поломок. Настоящую живость показывает только get_file, и она проверяется
    # у каждого трека перед скачиванием.
    stale = datetime.utcnow() - timedelta(days=RECHECK_AFTER_DAYS)
    touched = await session.scalar(
        select(func.count()).select_from(Track).where(Track.repair_checked_at.is_not(None))
    ) or 0
    fresh_queue = await session.scalar(
        select(func.count()).select_from(Track).where(
            (Track.tg_file_id.is_(None)) | (Track.created_at < BOT_SWAP),
            (Track.repair_checked_at.is_(None)) | (Track.repair_checked_at < stale),
        )
    ) or 0
    print(f"всего треков:                  {total}")
    print(f"заведены до переезда:          {suspect}  (живость проверяем поштучно)")
    print(f"заведены нынешним ботом:       {alive}")
    print(f"id погашен, ждут ремонта:      {waiting}")
    print(f"уже занимались:                {touched}")
    # Именно это число должно убывать от ночи к ночи. Если оно стоит на месте —
    # прогон крутится вхолостую, и раньше заметить это было нечем.
    print(f"осталось в очереди:            {fresh_queue}")


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

    🔴 И пропускаем тех, кем занимались недавно. Без этого условия очередь не
    двигалась вовсе: «заведён до переезда» истинно навсегда (восстановление
    сохраняет `created_at`), а неудачная попытка не оставляла следа. Замер 16.08
    за первую же ночь работы таймера: из 100 обработанных 11 оказались уже
    живыми и 17 не нашлись в источниках — 28% бюджета ушло в повтор, и доля
    растёт, пока прогон не начнёт целиком перебирать одно и то же, продолжая
    рапортовать о работе.
    """
    stale = datetime.utcnow() - timedelta(days=RECHECK_AFTER_DAYS)
    stmt = select(Track).where(
        (Track.tg_file_id.is_(None)) | (Track.created_at < BOT_SWAP),
        # NULL — ещё ни разу не трогали, такие идут в первую очередь
        (Track.repair_checked_at.is_(None)) | (Track.repair_checked_at < stale),
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
                    # Отметка нужна и здесь, иначе живой трек, заведённый до
                    # переезда, попадал бы в выборку каждую ночь до скончания
                    # века: условие «заведён до переезда» истинно навсегда.
                    fresh.repair_checked_at = datetime.utcnow()
                    await session.commit()
                    skipped += 1
                    continue
                fresh.tg_file_id = None
                fresh.meta_synced = False
                # Ставим ДО попытки: если процесс убьют посреди скачивания (а на
                # этом боксе такое бывало), трек не должен снова оказаться первым
                # в очереди на завтра.
                fresh.repair_checked_at = datetime.utcnow()
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
