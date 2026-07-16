"""Кнопка «✅ Проверить подписку» на экране обязательной подписки (TZ §14-17)."""
from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.handlers.start import build_cabinet_text
from app.keyboards.main_menu import main_menu_keyboard
from app.services.subscription import is_fully_subscribed

router = Router()

NOT_SUBSCRIBED_ALERT = "Не вижу подписку на все каналы. Подпишитесь и попробуйте снова."


@router.callback_query(F.data == "sub:check")
async def cb_subscription_check(callback: CallbackQuery) -> None:
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        subscribed = await is_fully_subscribed(
            session, callback.bot, user.id, user.telegram_id, force=True
        )
        if not subscribed:
            await callback.answer(NOT_SUBSCRIBED_ALERT, show_alert=True)
            return
        text = await build_cabinet_text(session, user)
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard())
    await callback.answer("✅ Подписка подтверждена")
