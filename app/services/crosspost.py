"""Кросс-пост новостей из ТГ-канала в сообщество ВК (wall.post).

Текст поста уходит на стену группы от её имени. Ошибки логируются и не
роняют бота — кросс-пост вторичен относительно публикации в Telegram.
"""
import asyncio
import logging

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

VK_API = "https://api.vk.com/method/wall.post"
VK_API_VERSION = "5.199"
VK_TIMEOUT_SEC = 15


def is_crosspost_configured() -> bool:
    return bool(settings.news_channel_id and settings.vk_token and settings.vk_group_id)


async def post_to_vk(text: str) -> bool:
    """Публикует текст на стену группы ВК. True — опубликовано."""
    if not text.strip():
        return False
    params = {
        "access_token": settings.vk_token,
        "v": VK_API_VERSION,
        "owner_id": str(-settings.vk_group_id),
        "from_group": "1",
        "message": text,
    }
    try:
        timeout = aiohttp.ClientTimeout(total=VK_TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.post(VK_API, data=params) as response:
                payload = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("ВК недоступен, кросс-пост не ушёл: %s", exc)
        return False
    if "error" in payload:
        logger.warning("ВК отклонил кросс-пост: %s", payload["error"].get("error_msg"))
        return False
    logger.info("Кросс-пост в ВК опубликован: post_id=%s", payload.get("response", {}).get("post_id"))
    return True
