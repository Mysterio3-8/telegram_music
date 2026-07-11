import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import settings
from app.db.base import init_db
from app.handlers import library, playlists, search, start, stubs, track_actions, upload


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан — скопируйте .env.example в .env и впишите токен")

    await init_db()
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_routers(
        start.router,
        library.router,
        playlists.router,
        search.router,
        upload.router,
        track_actions.router,
        stubs.router,
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
