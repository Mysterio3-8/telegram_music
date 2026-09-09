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
    donate_method_keyboard,
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
from app.services import donation_goals as goals
from app.services import wallet_pay
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


def _spaced(amount: int) -> str:
    """12345 → «12 345». Неразрывного пробела не берём: он ломает выравнивание
    в моноширинном блоке с полосой прогресса."""
    return f"{amount:,}".replace(",", " ")


async def _goal_block(session, lang: str) -> tuple[str, bool]:
    """Шапка экрана с текущей целью. ("", False) — сбора сейчас нет."""
    goal = await goals.active_goal(session)
    if goal is None:
        return "", False

    raised = await goals.goal_progress(session, goal.id)
    lines = [
        t("goal.block", lang).format(
            title=html.escape(goal.title),
            bar=goals.progress_bar(raised, goal.target_rub),
            percent=goals.progress_percent(raised, goal.target_rub),
            raised=_spaced(raised),
            target=_spaced(goal.target_rub),
        )
    ]
    left = goals.days_left(goal)
    if left is not None:
        if left > 0:
            lines.append(t("goal.days_left", lang).format(days=left))
        elif left == 0:
            lines.append(t("goal.last_day", lang))
        else:
            lines.append(t("goal.deadline_over", lang))
    if goal.reached_at is not None:
        lines.append(t("goal.reached", lang))
    return "\n".join(lines) + "\n\n", True


async def _is_anonymous(state: FSMContext) -> bool:
    """Выбор «анонимно» живёт в FSM, а не в профиле: это решение про КОНКРЕТНЫЙ
    донат, а не постоянная настройка человека."""
    data = await state.get_data()
    return bool(data.get("donate_anon"))


async def _show_donate_screen(
    message: Message, lang: str, edit: bool, *, anonymous: bool = False
) -> None:
    async with session_factory() as session:
        block, has_goal = await _goal_block(session, lang)
    text = block + _intro_text(lang)
    if anonymous:
        text += "\n\n<i>" + html.escape(t("donate.anon_hint", lang)) + "</i>"
    markup = donate_keyboard(lang, anonymous=anonymous, has_goal=has_goal)
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
    await _show_donate_screen(
        message, lang, edit=False, anonymous=await _is_anonymous(state)
    )


@router.callback_query(F.data == "don:open")
async def cb_open(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
    await _show_donate_screen(
        callback.message, lang, edit=True, anonymous=await _is_anonymous(state)
    )
    await callback.answer()


@router.callback_query(F.data == "don:anon")
async def cb_anon(callback: CallbackQuery, state: FSMContext) -> None:
    """Переключить анонимность. Экран перерисовывается целиком: подпись кнопки и
    пояснение под текстом должны меняться вместе, иначе человек видит кнопку
    «включено» без единого следа того, что именно включилось."""
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
    anonymous = not await _is_anonymous(state)
    await state.update_data(donate_anon=anonymous)
    await _show_donate_screen(callback.message, lang, edit=True, anonymous=anonymous)
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
    anonymous = await _is_anonymous(state)
    await state.set_state(None)
    await _start_payment(
        message, user.telegram_id, amount, lang, edit=False, anonymous=anonymous
    )


@router.callback_query(F.data.startswith("don:pay:"))
async def cb_pay(callback: CallbackQuery, state: FSMContext) -> None:
    # ⚠️ Состояние сбрасывается, но данные FSM (флаг анонимности) остаются:
    # set_state(None) чистит только состояние. Если однажды тут появится
    # state.clear(), выбор «анонимно» молча перестанет доезжать до платежа.
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
    await _start_payment(
        callback.message,
        user.telegram_id,
        int(raw),
        lang,
        edit=True,
        anonymous=await _is_anonymous(state),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("don:rub:") | F.data.startswith("don:ton:"))
async def cb_pay_method(callback: CallbackQuery, state: FSMContext) -> None:
    """Способ выбран — создаём платёж.

    Сумма проверяется здесь ЗАНОВО, а не берётся на веру из предыдущего экрана:
    callback_data приходит от клиента, и до этой кнопки можно дойти напрямую,
    минуя экран выбора.
    """
    await state.set_state(None)
    method, _, raw = callback.data.removeprefix("don:").partition(":")
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
    if not (raw.isascii() and raw.isdigit()) or not is_allowed_amount(int(raw)):
        await callback.answer(t("donate.bad_amount_short", lang), show_alert=True)
        return
    if method == "ton" and not wallet_pay.is_configured():
        # Способ мог отключиться, пока человек смотрел на экран.
        await callback.answer(t("donate.unavailable", lang), show_alert=True)
        return
    await _start_payment(
        callback.message,
        user.telegram_id,
        int(raw),
        lang,
        edit=True,
        anonymous=await _is_anonymous(state),
        method=method,
    )
    await callback.answer()


async def _offer_methods(message: Message, amount: int, lang: str, edit: bool) -> None:
    """Экран выбора способа оплаты. Показывается, только если TON доступен."""
    text = t("donate.method_title", lang).format(amount=amount)
    markup = donate_method_keyboard(amount, wallet_pay.ton_for_rub(amount), lang)
    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


async def _start_ton_payment(
    message: Message, telegram_id: int, amount: int, lang: str, edit: bool, anonymous: bool
) -> None:
    """Счёт в TON через Wallet Pay."""
    result = await wallet_pay.create_order(telegram_id, amount, anonymous=anonymous)
    if result is None:
        text = t("donate.error", lang)
        markup = donate_keyboard(lang, anonymous=anonymous)
    else:
        _order_id, link = result
        text = t("donate.ton_prompt", lang).format(
            amount=amount, ton=wallet_pay.ton_for_rub(amount)
        )
        markup = donate_pay_keyboard(link, lang)
    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


async def _start_payment(
    message: Message,
    telegram_id: int,
    amount: int,
    lang: str,
    edit: bool,
    *,
    anonymous: bool = False,
    method: str | None = None,
) -> None:
    """Создаёт платёж и показывает кнопку оплаты.

    `method=None` и доступный TON — сперва спрашиваем, чем платить. Когда TON
    выключен (нет ключа, нет курса или проба не пройдена), развилки нет вовсе и
    человек идёт прямо на кассу, как раньше.
    """
    if method is None and wallet_pay.is_configured():
        await _offer_methods(message, amount, lang, edit)
        return
    if method == "ton":
        await _start_ton_payment(message, telegram_id, amount, lang, edit, anonymous)
        return
    if not is_yookassa_configured():
        text = t("donate.unavailable", lang)
        if edit:
            await message.edit_text(text, reply_markup=donate_keyboard(lang), parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=donate_keyboard(lang), parse_mode="HTML")
        return

    url = await create_donation_payment(
        telegram_id, settings.bot_username, amount, anonymous=anonymous
    )
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
        has_goal = await goals.active_goal(session) is not None
    text = _format_top(rows, lang)
    if rank is not None:
        text += "\n\n" + t("donate.your_place", lang).format(
            rank=rank, total=_spaced(mine)
        )
    await callback.message.edit_text(
        text,
        reply_markup=donate_top_keyboard(lang, showing_goal=False, has_goal=has_goal),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "don:goaltop")
async def cb_goal_top(callback: CallbackQuery, state: FSMContext) -> None:
    """Вклад в ТЕКУЩУЮ цель — отдельный список от общего топа за всё время.

    Смысл в том, что он мотивирует добить именно этот сбор: в общем топе новичок
    против давнего спонсора не имеет шансов, а здесь все начинают с нуля.
    """
    await state.set_state(None)
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
        goal = await goals.active_goal(session)
        if goal is None:
            # Цель могли закрыть, пока человек смотрел на экран.
            await callback.answer(t("goal.none", lang), show_alert=True)
            return
        rows = await goals.goal_top(session, goal.id)
        raised = await goals.goal_progress(session, goal.id)

    if not rows:
        text = t("goal.top_empty", lang)
    else:
        lines = [t("goal.top_title", lang).format(title=html.escape(goal.title)), ""]
        for index, (row_user, total) in enumerate(rows, start=1):
            prefix = _MEDALS[index - 1] if index <= len(_MEDALS) else f"{index}."
            lines.append(f"{prefix} {html.escape(display_name(row_user))} — {_spaced(total)} ₽")
        text = "\n".join(lines)

    text += "\n\n" + t("goal.block", lang).format(
        title=html.escape(goal.title),
        bar=goals.progress_bar(raised, goal.target_rub),
        percent=goals.progress_percent(raised, goal.target_rub),
        raised=_spaced(raised),
        target=_spaced(goal.target_rub),
    )
    await callback.message.edit_text(
        text,
        reply_markup=donate_top_keyboard(lang, showing_goal=True, has_goal=True),
        parse_mode="HTML",
    )
    await callback.answer()


async def show_donate_from_start(message: Message, lang: str) -> None:
    """Экран доната по deep-link `/start donate` — для кнопки под постами канала."""
    await _show_donate_screen(message, lang, edit=False)
