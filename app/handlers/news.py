"""Новостной канал → автокросс-пост в ВК.

Бот — админ новостного канала: каждый пост (текст или подпись к медиа)
уходит на стену сообщества ВК. К тексту добавляется ссылка на оригинал,
если у канала есть username.
"""
import logging

from aiogram import Router
from aiogram.types import Message

from app.config import settings
from app.services.crosspost import is_crosspost_configured, post_to_vk

logger = logging.getLogger(__name__)

router = Router()


@router.channel_post()
async def on_channel_post(message: Message) -> None:
    if not is_crosspost_configured():
        return
    if message.chat.id != settings.news_channel_id:
        return
    text = message.text or message.caption or ""
    if not text.strip():
        return  # медиа без подписи — нечего постить в ВК
    if message.chat.username:
        text += f"\n\nИсточник: https://t.me/{message.chat.username}/{message.message_id}"
    posted = await post_to_vk(text)
    if not posted:
        logger.warning("Кросс-пост поста %s не удался", message.message_id)
