import asyncio
import logging

from aiogram import Bot, Dispatcher, F

from app.bot_commands import setup_bot_commands
from app.config import settings
from app.fsm import build_storage
from app.handlers import (
    admin,
    admin_broadcast,
    admin_telegram_channel,
    admin_upload_minus,
    admin_youtube,
    contests,
    errors,
    inline,
    language,
    library,
    news,
    player,
    playlists,
    premium,
    quick_search,
    referral,
    search,
    settings as settings_screen,
    start,
    stubs,
    subscription,
    track_actions,
    transfer,
    upload,
)
from app.middlewares.ads import AdMiddleware
from app.middlewares.i18n import I18nMiddleware
from app.middlewares.subscription import SubscriptionMiddleware
from app.middlewares.throttling import ThrottlingMiddleware
from app.middlewares.timing import TimingMiddleware


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

    # Замер — самым первым: нужно полное время ожидания живого человека,
    # включая работу антиспама и проверки подписки
    timing_middleware = TimingMiddleware()
    dp.message.middleware(timing_middleware)
    dp.callback_query.middleware(timing_middleware)

    # Антиспам — вторым: флуд должен гаситься до проверки подписки, БД и поиска
    throttling_middleware = ThrottlingMiddleware()
    dp.message.middleware(throttling_middleware)
    dp.callback_query.middleware(throttling_middleware)

    # До гейта подписки: его экран — первое, что видит новичок, и он тоже переводится
    i18n_middleware = I18nMiddleware()
    dp.message.middleware(i18n_middleware)
    dp.callback_query.middleware(i18n_middleware)

    subscription_middleware = SubscriptionMiddleware()
    dp.message.middleware(subscription_middleware)
    dp.callback_query.middleware(subscription_middleware)

    ad_middleware = AdMiddleware(frequency=settings.ad_frequency)
    dp.message.middleware(ad_middleware)
    dp.callback_query.middleware(ad_middleware)

    # Личный кабинет — только в личке (пункт 6 спеки 13.08). Всё это диалоговые
    # мастера и персональные экраны: загрузка спрашивает название, потом
    # исполнителя, а в общем чате следующее сообщение придёт от другого человека,
    # и мастер соберёт из двух собеседников одну кашу. Плюс чужие настройки,
    # плейлисты и админка в общем чате не нужны никому.
    #
    # Фильтр вешается тут, а не в каждом хендлере, сознательно: забыть его в
    # одном из полутора десятков роутеров — вопрос времени, а последствие
    # (админка, открытая из группы) слишком дорогое.
    for personal in (
        start, subscription, language, settings_screen, library, playlists, search,
        upload, transfer, premium, referral, player, contests, admin, admin_broadcast,
        admin_upload_minus, admin_youtube, admin_telegram_channel, track_actions, stubs,
    ):
        personal.router.message.filter(F.chat.type == "private")
        personal.router.callback_query.filter(F.message.chat.type == "private")

    dp.include_routers(
        errors.router,  # глобальный обработчик — ловит исключения из любого хендлера ниже
        start.router,
        subscription.router,
        language.router,
        settings_screen.router,
        library.router,
        playlists.router,
        search.router,
        upload.router,
        transfer.router,
        premium.router,
        referral.router,
        player.router,
        contests.router,
        admin.router,  # до track_actions: перехватывает ta:edit
        admin_broadcast.router,
        admin_upload_minus.router,
        admin_youtube.router,
        admin_telegram_channel.router,
        track_actions.router,
        inline.router,  # inline_query — вне гейта подписки (middleware только message/callback)
        news.router,  # channel_post новостного канала → кросс-пост в ВК
        quick_search.router,  # свободный текст боту → трек (регистрируется поздно, после FSM)
        stubs.router,
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
