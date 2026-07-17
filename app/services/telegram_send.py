"""Отправка аудио в чат пользователя из API-процесса (ТЗ §9: «Скачать» в Mini App).

Прямой вызов HTTP Bot API по кэшированному tg_file_id — мгновенно и без
aiogram-зависимости в API. Файл без tg_file_id (ещё не проходил через бота)
отправить нельзя — вызывающий код возвращает понятную ошибку.
"""
import logging

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


async def send_audio_by_file_id(
    chat_id: int, tg_file_id: str, title: str | None = None, performer: str | None = None
) -> bool:
    payload: dict = {"chat_id": chat_id, "audio": tg_file_id}
    if title:
        payload["title"] = title
    if performer:
        payload["performer"] = performer
    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                f"{TELEGRAM_API}/bot{settings.bot_token}/sendAudio", json=payload
            ) as response:
                if response.status != 200:
                    logger.error("sendAudio %s: %s", response.status, await response.text())
                    return False
                return True
    except aiohttp.ClientError:
        logger.exception("Telegram API недоступен (sendAudio chat=%s)", chat_id)
        return False
