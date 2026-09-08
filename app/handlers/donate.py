"""Экран «Поддержать»: выбор суммы, оплата через ЮKassa, рейтинг спонсоров.

Инвариант проекта: здесь только роутинг и форматирование текста. Суммы,
границы и рейтинг считает app/services/donations.py.
"""
import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.db.base import session_factory
from app.handlers.common import ensure_user
from app.i18n import t
from app.keyboards.donate import (
    donate_cancel_keyboard,
    donate_keyboard,
    donate_pay_keyboard,
    donate_top_keyboard,
)
from app.services.donations import (
    MAX_AMOUNT_RUB,
    MIN_AMOUNT_RUB,
    TOP_LIMIT,
    display_name,
    is_allowed_amount,
    parse_amount,
    top_sponsors,
    user_rank,
    user_total,
)
from app.services.users import user_language
from app.services.yookassa_payments import create_donation_payment, is_yookassa_configured

router = Router()
logger = logging.getLogger(__name__)

# Медали первой тройке — дешёвый способ сделать список нарядным.
_MEDALS = ("🥇", "🥈", "🥉")


class DonateStates(StatesGroup):
    waiting_amount = State()


def _intro_text(lang: str) -> str:
    return t("donate.intro", lang)


async def _show_donate_screen(message: Message, lang: str, edit: bool) -> None:
    text = _intro_text(lang)
    markup = donate_keyboard(lang)
    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.message(Command("donate"))
async def cmd_donate(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        lang = user_language(user)
    await _show_donate_screen(message, lang, edit=False)


@router.callback_query(F.data == "don:open")
async def cb_open(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
    await _show_donate_screen(callback.message, lang, edit=True)
    await callback.answer()


@router.callback_query(F.data == "don:custom")
async def cb_custom(callback: CallbackQuery, state: FSMContext) -> None:
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
    await state.set_state(DonateStates.waiting_amount)
    await callback.message.edit_text(
        t("donate.custom_prompt", lang).format(min=MIN_AMOUNT_RUB, max=MAX_AMOUNT_RUB),
        reply_markup=donate_cancel_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(DonateStates.waiting_amount)
async def process_custom_amount(message: Message, state: FSMContext) -> None:
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        lang = user_language(user)
    amount = parse_amount(message.text or "")
    if amount is None:
        # Состояние не сбрасываем — человек просто пробует снова.
        await message.answer(
            t("donate.bad_amount", lang).format(min=MIN_AMOUNT_RUB, max=MAX_AMOUNT_RUB),
            reply_markup=donate_cancel_keyboard(lang),
            parse_mode="HTML",
        )
        return
    await state.set_state(None)
    await _start_payment(message, user.telegram_id, amount, lang, edit=False)


@router.callback_query(F.data.startswith("don:pay:"))
async def cb_pay(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    raw = callback.data.removeprefix("don:pay:")
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
    # callback_data приходит от клиента и подделывается — проверяем сумму, а не
    # верим кнопке. Иначе можно было бы прислать don:pay:1 или отрицательное.
    # isascii() обязателен рядом с isdigit(): «²» проходит isdigit(), но int()
    # на нём падает — то же самое, что в parse_amount.
    if not (raw.isascii() and raw.isdigit()) or not is_allowed_amount(int(raw)):
        await callback.answer(t("donate.bad_amount_short", lang), show_alert=True)
        return
    await _start_payment(callback.message, user.telegram_id, int(raw), lang, edit=True)
    await callback.answer()


async def _start_payment(
    message: Message, telegram_id: int, amount: int, lang: str, edit: bool
) -> None:
    """Создаёт платёж в ЮKassa и показывает кнопку оплаты."""
    if not is_yookassa_configured():
        text = t("donate.unavailable", lang)
        if edit:
            await message.edit_text(text, reply_markup=donate_keyboard(lang), parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=donate_keyboard(lang), parse_mode="HTML")
        return

    url = await create_donation_payment(telegram_id, settings.bot_username, amount)
    if url is None:
        text = t("donate.error", lang)
        if edit:
            await message.edit_text(text, reply_markup=donate_keyboard(lang), parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=donate_keyboard(lang), parse_mode="HTML")
        return

    text = t("donate.pay_prompt", lang).format(amount=amount)
    markup = donate_pay_keyboard(url, lang)
    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


def _format_top(rows: list[tuple[object, int]], lang: str) -> str:
    if not rows:
        return t("donate.top_empty", lang)
    lines = [t("donate.top_title", lang).format(limit=TOP_LIMIT), ""]
    for index, (user, total) in enumerate(rows, start=1):
        prefix = _MEDALS[index - 1] if index <= len(_MEDALS) else f"{index}."
        # Экранируем, хотя юзернейм Telegram ограничен латиницей и цифрами:
        # список публичный, и полагаться на чужие ограничения в HTML не стоит.
        name = html.escape(display_name(user))
        lines.append(f"{prefix} {name} — {total:,} ₽".replace(",", " "))
    return "\n".join(lines)


@router.callback_query(F.data == "don:top")
async def cb_top(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
        rows = await top_sponsors(session)
        mine = await user_total(session, user.id)
        rank = await user_rank(session, user.id)
    text = _format_top(rows, lang)
    if rank is not None:
        text += "\n\n" + t("donate.your_place", lang).format(
            rank=rank, total=f"{mine:,}".replace(",", " ")
        )
    await callback.message.edit_text(
        text, reply_markup=donate_top_keyboard(lang), parse_mode="HTML"
    )
    await callback.answer()


async def show_donate_from_start(message: Message, lang: str) -> None:
    """Экран доната по deep-link `/start donate` — для кнопки под постами канала."""
    await _show_donate_screen(message, lang, edit=False)
