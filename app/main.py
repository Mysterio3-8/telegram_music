import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import settings
from app.fsm import build_storage
from app.handlers import (
    admin,
    library,
    player,
    playlists,
    premium,
    search,
    start,
    stubs,
    track_actions,
    upload,
)
from app.middlewares.ads import AdMiddleware


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан — скопируйте .env.example в .env и впишите токен")

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=build_storage())

    ad_middleware = AdMiddleware(frequency=settings.ad_frequency)
    dp.message.middleware(ad_middleware)
    dp.callback_query.middleware(ad_middleware)

    dp.include_routers(
        start.router,
        library.router,
        playlists.router,
        search.router,
        upload.router,
        premium.router,
        player.router,
        admin.router,  # до track_actions: перехватывает ta:edit
        track_actions.router,
        stubs.router,
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
