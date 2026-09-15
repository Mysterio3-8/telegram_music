"""Единый журнал событий для аналитики (15.09).

Владелец: «собирать очень много статистики, всего подряд — и бизнес, и
прослушивания, и жанры, и настроения — чтобы анализировать и улучшать».

Правила:
- имена и источники — из белых списков: опечатка в коде падает в тесте, а не
  плодит в базе «listne» рядом с «listen»;
- свойства — компактный JSON до 1 КБ; больше — пишем пометку, а не обрезок
  (обрезанный JSON не распарсить);
- аналитика не ломает сценарий: ошибка записи логируется и глотается.

Жанр и настроение в события не копируются — отчёт берёт их из треков.
"""
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalyticsEvent

logger = logging.getLogger(__name__)

EVENT_NAMES = frozenset(
    {
        # прослушивание и выдача
        "listen",          # трек начали слушать / отдали аудио (дедуп 30 сек — stats.record_event)
        "download",        # трек прислали файлом в чат
        "play_complete",   # Mini App: дослушал до конца
        "play_skip",       # Mini App: переключил раньше конца (props.position_pct)
        # поиск и навигация
        "search",          # запрос (props.results — сколько нашлось, если известно)
        "screen_view",     # Mini App: открыт экран (props.screen)
        # рост и деньги
        "share_click",     # нажали «поделиться»
        "paywall_view",    # Mini App: показан пэйвол
        "reminder_sent",   # бот отправил напоминание (props.kind)
    }
)
SOURCES = frozenset({"bot", "miniapp", "worker", "system", "unknown"})
MAX_PROPS_BYTES = 1000


def encode_props(props: dict | None) -> str | None:
    if not props:
        return None
    payload = json.dumps(props, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(payload.encode("utf-8")) > MAX_PROPS_BYTES:
        return json.dumps({"truncated": True}, separators=(",", ":"))
    return payload


def build_event(
    name: str,
    *,
    source: str,
    user_id: int | None = None,
    track_id: int | None = None,
    props: dict | None = None,
) -> AnalyticsEvent:
    """Событие без записи — для вызывающих, у которых свой commit."""
    if name not in EVENT_NAMES:
        raise ValueError(f"неизвестное событие аналитики: {name}")
    if source not in SOURCES:
        raise ValueError(f"неизвестный источник аналитики: {source}")
    return AnalyticsEvent(
        name=name, source=source, user_id=user_id, track_id=track_id, props=encode_props(props)
    )


async def track_event(
    session: AsyncSession,
    name: str,
    *,
    source: str,
    user_id: int | None = None,
    track_id: int | None = None,
    props: dict | None = None,
) -> None:
    event = build_event(name, source=source, user_id=user_id, track_id=track_id, props=props)
    try:
        session.add(event)
        await session.commit()
    except Exception:  # noqa: BLE001 — аналитика не ломает сценарий
        logger.warning("Аналитика: не записано событие %s user=%s", name, user_id, exc_info=True)
        await session.rollback()
