import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.bot_commands import setup_bot_commands
from app.config import settings
from app.fsm import build_storage
from app.handlers import (
    admin,
    admin_broadcast,
    admin_telegram_channel,
    admin_upload_minus,
    admin_youtube,
    inline,
    library,
    news,
    player,
    playlists,
    premium,
    search,
    start,
    stubs,
    subscription,
    track_actions,
    transfer,
    upload,
)
from app.middlewares.ads import AdMiddleware
from app.middlewares.subscription import SubscriptionMiddleware


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан — скопируйте .env.example в .env и впишите токен")

    bot = Bot(token=settings.bot_token)
    await setup_bot_commands(bot)
    dp = Dispatcher(storage=build_storage())

    subscription_middleware = SubscriptionMiddleware()
    dp.message.middleware(subscription_middleware)
    dp.callback_query.middleware(subscription_middleware)

    ad_middleware = AdMiddleware(frequency=settings.ad_frequency)
    dp.message.middleware(ad_middleware)
    dp.callback_query.middleware(ad_middleware)

    dp.include_routers(
        start.router,
        subscription.router,
        library.router,
        playlists.router,
        search.router,
        upload.router,
        transfer.router,
        premium.router,
        player.router,
        admin.router,  # до track_actions: перехватывает ta:edit
        admin_broadcast.router,
        admin_upload_minus.router,
        admin_youtube.router,
        admin_telegram_channel.router,
        track_actions.router,
        inline.router,  # inline_query — вне гейта подписки (middleware только message/callback)
        news.router,  # channel_post новостного канала → кросс-пост в ВК
        stubs.router,
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
