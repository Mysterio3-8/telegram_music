"""Пост о цели в канале: публикация и живая перерисовка прогресса.

⚠️ Работа идёт голым HTTP к Bot API, без aiogram, — как в
[telegram_send.py](app/services/telegram_send.py), и по той же причине, только
здесь она жёстче. Донат подтверждается вебхуком ЮKassa, а вебхук принимает
`tg-music-api` (uvicorn), где aiogram нет вообще. Импортируй мы Bot — пост
обновлялся бы откуда угодно, кроме того единственного места, где становится
известно, что деньги пришли.

Ошибка Telegram здесь НИКОГДА не роняет вызывающий код: пост в канале — витрина,
а деньги уже зачислены. Уронить обработку платежа из-за неудачной правки
картинки значило бы ответить кассе ошибкой и получить повтор уведомления.
"""
import logging

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import DonationGoal
from app.services import donation_goals as goals
from app.services.donations import display_name

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
TIMEOUT_SEC = 15
# Подпись к фото у Telegram ограничена 1024 символами, обычное сообщение — 4096.
# Пост с картинкой приходится держать в более узких рамках.
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096


def _escape(text: str) -> str:
    """Экранирование под parse_mode=HTML.

    Название цели и имена пишут люди, а `&` в «Сервер & домен» без экранирования
    делает пост невалидным — Telegram отвечает ошибкой и НЕ публикует его вовсе.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_post(
    goal: DonationGoal,
    raised: int,
    recent: list[tuple[object, int, bool]],
    *,
    with_recent: bool = True,
) -> str:
    """Текст поста: заголовок, полоса, сумма, срок, последние донаты.

    Язык один — русский: пост уходит в конкретный канал с конкретной аудиторией,
    а не каждому человеку в его интерфейсе. Экраны в боте переведены отдельно.
    """
    percent = goals.progress_percent(raised, goal.target_rub)
    bar = goals.progress_bar(raised, goal.target_rub)

    lines = [f"🎯 <b>{_escape(goal.title)}</b>"]
    if goal.description:
        lines.append("")
        lines.append(_escape(goal.description))
    lines.append("")
    lines.append(f"<code>{bar}</code> {percent}%")
    lines.append(f"Собрано <b>{raised:,} ₽</b> из <b>{goal.target_rub:,} ₽</b>".replace(",", " "))

    left = goals.days_left(goal)
    if left is not None:
        if left > 0:
            lines.append(f"⏳ Осталось дней: {left}")
        elif left == 0:
            lines.append("⏳ Последний день сбора")
        else:
            # Срок вышел, но цель ещё открыта — решение закрыть за владельцем.
            lines.append("⏳ Срок вышел, сбор продолжается")

    if goal.reached_at is not None:
        lines.append("")
        lines.append("✅ <b>Цель собрана. Спасибо каждому, кто вложился!</b>")

    if with_recent and recent:
        lines.append("")
        lines.append("<b>Последние:</b>")
        for user, amount, anonymous in recent:
            who = "Аноним" if anonymous else _escape(display_name(user))
            lines.append(f"▪️ {who} — {amount} ₽")

    lines.append("")
    lines.append("<i>Поддержка добровольная. Взамен ничего не выдаётся.</i>")
    return "\n".join(lines)


def _fit(text: str, limit: int) -> str:
    """Ужать пост под лимит Telegram, отрезая по строкам, а не по символам.

    Обрубок по символам легко разрывает HTML-тег пополам, и тогда Telegram
    отказывается публиковать пост целиком.
    """
    if len(text) <= limit:
        return text
    lines = text.split("\n")
    while lines and len("\n".join(lines)) > limit:
        lines.pop()
    return "\n".join(lines)


def _keyboard() -> dict:
    """Кнопка «Поддержать» под постом — вглубь бота, сразу на экран доната."""
    username = settings.bot_username
    return {
        "inline_keyboard": [
            [{"text": "❤️ Поддержать", "url": f"https://t.me/{username}?start=donate"}]
        ]
    }


async def _call(method: str, payload: dict) -> dict | None:
    """Вызов Bot API. None — не получилось; причина уже в журнале."""
    if not settings.bot_token:
        logger.warning("goal_post.%s: BOT_TOKEN не задан", method)
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.post(
                f"{TELEGRAM_API}/bot{settings.bot_token}/{method}", json=payload
            ) as response:
                body = await response.json(content_type=None)
                if response.status != 200 or not body.get("ok"):
                    description = (body or {}).get("description", "")
                    # Правка поста, который и так актуален, — не ошибка, а норма:
                    # два доната на одну сумму подряд дают тот же самый текст.
                    if "message is not modified" in description:
                        return None
                    logger.error("goal_post.%s %s: %s", method, response.status, description)
                    return None
                return body.get("result")
    except aiohttp.ClientError:
        logger.exception("Telegram API недоступен (goal_post.%s)", method)
        return None
    except Exception:  # noqa: BLE001 — витрина не должна ронять обработку платежа
        logger.exception("goal_post.%s: неожиданная ошибка", method)
        return None


async def publish(session: AsyncSession, goal: DonationGoal, chat_id: int) -> bool:
    """Опубликовать пост о цели в канале и запомнить его id для будущих правок.

    Повторная публикация заводит НОВЫЙ пост и забывает старый: так и задумано —
    старый остаётся в канале памятником, а редактировать мы будем свежий.
    """
    raised = await goals.goal_progress(session, goal.id)
    recent = await goals.recent_donations(session, goal.id)
    text = render_post(goal, raised, recent)

    if goal.image_file_id:
        result = await _call(
            "sendPhoto",
            {
                "chat_id": chat_id,
                "photo": goal.image_file_id,
                "caption": _fit(text, CAPTION_LIMIT),
                "parse_mode": "HTML",
                "reply_markup": _keyboard(),
            },
        )
    else:
        result = await _call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": _fit(text, TEXT_LIMIT),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": _keyboard(),
            },
        )
    if not result:
        return False

    goal.channel_chat_id = chat_id
    goal.channel_message_id = result["message_id"]
    await session.commit()
    logger.info("Пост цели #%s опубликован: chat=%s msg=%s", goal.id, chat_id, result["message_id"])
    return True


async def refresh(session: AsyncSession, goal: DonationGoal) -> bool:
    """Перерисовать опубликованный пост. False — поста нет или Telegram отказал."""
    if not goal.channel_chat_id or not goal.channel_message_id:
        return False

    raised = await goals.goal_progress(session, goal.id)
    recent = await goals.recent_donations(session, goal.id)
    text = render_post(goal, raised, recent)

    # У поста с картинкой правится подпись, у обычного — текст. Перепутать
    # нельзя: editMessageText на фото-посте отвечает отказом.
    if goal.image_file_id:
        method, field, limit = "editMessageCaption", "caption", CAPTION_LIMIT
    else:
        method, field, limit = "editMessageText", "text", TEXT_LIMIT

    payload = {
        "chat_id": goal.channel_chat_id,
        "message_id": goal.channel_message_id,
        field: _fit(text, limit),
        "parse_mode": "HTML",
        "reply_markup": _keyboard(),
    }
    if method == "editMessageText":
        payload["disable_web_page_preview"] = True
    return await _call(method, payload) is not None


async def refresh_active(session: AsyncSession) -> bool:
    """Перерисовать пост текущей цели. Зовётся после каждого зачтённого доната."""
    goal = await goals.active_goal(session)
    if goal is None:
        return False
    return await refresh(session, goal)
