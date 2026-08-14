"""Настройки выдачи: формат файла (mp3 или оригинал автора).

Экран отдельный от выбора языка сознательно: язык человек трогает один раз при
входе, а формат — это Premium-функция, которую надо показывать и объяснять.
"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.i18n import t
from app.keyboards.settings import quality_keyboard
from app.services.original_audio import QUALITY_BEST
from app.services.premium import is_premium_active
from app.services.users import set_audio_quality, user_language

router = Router()


def _screen_text(lang: str) -> str:
    return t("settings.title", lang) + "\n\n" + t("settings.quality_hint", lang)


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        lang, quality = user_language(user), user.audio_quality
    await message.answer(
        _screen_text(lang),
        reply_markup=quality_keyboard(quality, lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:settings")
async def cb_settings_screen(callback: CallbackQuery) -> None:
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang, quality = user_language(user), user.audio_quality
    await callback.message.edit_text(
        _screen_text(lang),
        reply_markup=quality_keyboard(quality, lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set:q:"))
async def cb_set_quality(callback: CallbackQuery) -> None:
    choice = callback.data.removeprefix("set:q:")
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
        # Не-Premium выбор не сохраняем и честно объясняем почему. Сохранить
        # «на будущее» было бы хуже: человек ушёл бы с экрана в уверенности, что
        # получает лучшее качество, и не понял бы, почему звучит как раньше.
        if choice == QUALITY_BEST and not is_premium_active(user):
            await callback.answer(t("settings.quality_premium_only", lang), show_alert=True)
            return
        quality = await set_audio_quality(session, user, choice)

    await callback.message.edit_text(
        _screen_text(lang),
        reply_markup=quality_keyboard(quality, lang),
        parse_mode="HTML",
    )
    notice = (
        t("settings.quality_saved_best", lang)
        if quality == QUALITY_BEST
        else t("settings.quality_saved_mp3", lang)
    )
    await callback.answer(notice, show_alert=quality == QUALITY_BEST)

