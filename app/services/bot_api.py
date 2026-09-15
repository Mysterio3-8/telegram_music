"""Лёгкий клиент Bot API для процесса API Mini App — без aiogram.

🔴 Зачем (цикл 7, 15.09). Замер импортов API: aiogram.types+methods — +38 МБ,
42% всей Python-кучи процесса, и 6.5 из 8.6 сек импорта. А нужны API из него
три метода: getChatMember (гейт подписки, конкурсы), getMe и скачивание файла
(аудио, которого нет в кэше). Бот и воркеры по-прежнему живут на aiogram.

Интерфейс повторяет используемую часть `aiogram.Bot` (`get_chat_member`,
`get_me`, `download`), поэтому сервисы принимают любой из двух клиентов.

⚠️ Токен бота — в URL каждого запроса. Поэтому текст ошибки строится из имени
метода и класса исключения, а исходное исключение отбрасывается (`from None`):
сообщение aiohttp может содержать адрес целиком, и токен уехал бы в журнал.
"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import BinaryIO

import aiohttp

from app.config import settings

TELEGRAM_API = "https://api.telegram.org"
_CALL_TIMEOUT = aiohttp.ClientTimeout(total=30)
# Скачивание до 20 МБ: общий потолок не ставим, чтобы медленный канал не рвал
# рабочую закачку, но зависшее чтение обрывается.
_SESSION_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=60)
_DOWNLOAD_CHUNK = 256 * 1024


class BotApiError(Exception):
    """Telegram ответил ошибкой или не ответил вовсе."""


class BotApi:
    def __init__(self, token: str | None = None) -> None:
        self._token = token or settings.bot_token
        self._http: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "BotApi":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    def _session(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(timeout=_SESSION_TIMEOUT)
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.close()
            self._http = None

    async def _call(self, method: str, **params) -> dict:
        url = f"{TELEGRAM_API}/bot{self._token}/{method}"
        try:
            async with self._session().post(url, json=params, timeout=_CALL_TIMEOUT) as response:
                status = response.status
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            raise BotApiError(f"{method}: {exc.__class__.__name__}") from None
        if not isinstance(payload, dict) or not payload.get("ok"):
            description = payload.get("description") if isinstance(payload, dict) else None
            raise BotApiError(f"{method}: {description or f'HTTP {status}'}")
        return payload.get("result")

    async def get_me(self) -> SimpleNamespace:
        return SimpleNamespace(**await self._call("getMe"))

    async def get_chat_member(self, chat_id: int | str, user_id: int) -> SimpleNamespace:
        """Объект с `.status` («member», «left», «restricted»…) и, у restricted, `.is_member`."""
        return SimpleNamespace(**await self._call("getChatMember", chat_id=chat_id, user_id=user_id))

    async def download(self, file_id: str, destination: str | Path | BinaryIO) -> None:
        """getFile + скачивание. destination — путь (пишем в файл) или файловый объект."""
        info = await self._call("getFile", file_id=file_id)
        file_path = (info or {}).get("file_path")
        if not file_path:
            raise BotApiError("getFile: нет file_path")
        url = f"{TELEGRAM_API}/file/bot{self._token}/{file_path}"
        try:
            async with self._session().get(url) as response:
                if response.status != 200:
                    raise BotApiError(f"download: HTTP {response.status}")
                if isinstance(destination, (str, Path)):
                    with open(destination, "wb") as target:
                        async for chunk in response.content.iter_chunked(_DOWNLOAD_CHUNK):
                            target.write(chunk)
                else:
                    async for chunk in response.content.iter_chunked(_DOWNLOAD_CHUNK):
                        destination.write(chunk)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise BotApiError(f"download: {exc.__class__.__name__}") from None
