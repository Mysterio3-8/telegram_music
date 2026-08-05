"""Выбор языка интерфейса (заготовка мультиязычности).

Русский и английский переведены полностью, остальные языки выбираются, но пока
показывают английский — об этом честно предупреждаем при выборе.
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.i18n import is_translated, t
from app.keyboards.main_menu import language_keyboard
from app.services.users import set_user_language, user_language

router = Router()


@router.callback_query(F.data == "menu:lang")
async def cb_language_screen(callback: CallbackQuery) -> None:
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
    await callback.message.edit_text(
        t("lang.title", lang), reply_markup=language_keyboard(lang), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lang:set:"))
async def cb_language_set(callback: CallbackQuery) -> None:
    code = callback.data.removeprefix("lang:set:")
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = await set_user_language(session, user, code)
    await callback.message.edit_text(
        t("lang.title", lang), reply_markup=language_keyboard(lang), parse_mode="HTML"
    )
    notice = t("lang.saved", lang) if is_translated(lang) else t("lang.pending", lang)
    await callback.answer(notice, show_alert=not is_translated(lang))
