"""Настройки выдачи: качество файла и обложка отдельной картинкой.

Экран отдельный от выбора языка сознательно: язык человек трогает один раз при
входе, а качество — Premium-функция, которую надо показывать и объяснять.
"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.i18n import t
from app.keyboards.settings import settings_keyboard
from app.services.original_audio import QUALITY_BEST
from app.services.premium import is_premium_active
from app.services.users import set_audio_quality, toggle_cover_as_file, user_language

router = Router()


def _screen_text(lang: str) -> str:
    return "\n\n".join(
        (t("settings.title", lang), t("settings.quality_hint", lang), t("settings.cover_hint", lang))
    )


async def _show(target: Message | CallbackQuery, edit: bool) -> None:
    """Рисует экран по текущему состоянию пользователя.

    Общая функция на команду и на все нажатия: три копии одного и того же вызова
    расходились бы при первой же правке текста.
    """
    source = target.from_user
    async with session_factory() as session:
        user = await ensure_user(session, source)
        lang, quality, cover = user_language(user), user.audio_quality, user.cover_as_file
    markup = settings_keyboard(quality, cover, lang)
    if edit:
        await target.message.edit_text(_screen_text(lang), reply_markup=markup, parse_mode="HTML")
    else:
        await target.answer(_screen_text(lang), reply_markup=markup, parse_mode="HTML")


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    await _show(message, edit=False)


@router.callback_query(F.data == "menu:settings")
async def cb_settings_screen(callback: CallbackQuery) -> None:
    await _show(callback, edit=True)
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

    await _show(callback, edit=True)
    notice = (
        t("settings.quality_saved_best", lang)
        if quality == QUALITY_BEST
        else t("settings.quality_saved_mp3", lang)
    )
    await callback.answer(notice, show_alert=quality == QUALITY_BEST)


@router.callback_query(F.data == "set:cover")
async def cb_toggle_cover(callback: CallbackQuery) -> None:
    """Обложка отдельной картинкой. Не Premium: это не про качество, а про то,
    как человеку удобнее складывать музыку у себя."""
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
        enabled = await toggle_cover_as_file(session, user)

    await _show(callback, edit=True)
    await callback.answer(t("settings.cover_on" if enabled else "settings.cover_off", lang))
