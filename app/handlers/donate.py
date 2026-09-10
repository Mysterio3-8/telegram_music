"""Экран «Поддержать»: выбор суммы, оплата через ЮKassa, рейтинг спонсоров.

Инвариант проекта: здесь только роутинг и форматирование текста. Суммы,
границы и рейтинг считает app/services/donations.py.
"""
import html
import logging
from urllib.parse import quote

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
    goal_screen_keyboard,
    goal_share_keyboard,
    ton_manual_keyboard,
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
from app.services import goal_post
from app.services import crypto_pay
from app.services import ton_donations
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


def _ton_available() -> bool:
    """Есть ли хоть один рабочий путь оплаты в TON.

    Их два, и порядок не случаен: Crypto Pay даёт счёт в рублях, оплату в один
    тап и уведомление с подписью, а прямой перевод на кошелёк работает вообще
    без ключей, но требует от человека скопировать адрес и метку. Поэтому
    Crypto Pay — основной, прямой перевод — запасной.
    """
    return crypto_pay.is_configured() or ton_donations.is_configured()


def _goal_link() -> str:
    """Ссылка, которая открывает сбор прямо в боте.

    Именно её человек кидает другу или выкладывает в другую соцсеть: она ведёт
    не на пост в канале, а в бота, где сразу видно прогресс и стоит кнопка
    оплаты. Пост в канале даётся отдельной кнопкой — он нужен тем, кто хочет
    показать сбор внутри Telegram.
    """
    return f"https://t.me/{settings.bot_username}?start=goal"


async def _goal_screen(message: Message, lang: str, edit: bool) -> bool:
    """Экран текущего сбора. False — сбора сейчас нет."""
    async with session_factory() as session:
        goal = await goals.active_goal(session)
        if goal is None:
            return False
        raised = await goals.goal_progress(session, goal.id)
        recent = await goals.recent_donations(session, goal.id)
        url = await goal_post.post_url(goal)

    lines = [
        t("goal.block", lang).format(
            title=html.escape(goal.title),
            bar=goals.progress_bar(raised, goal.target_rub),
            percent=goals.progress_percent(raised, goal.target_rub),
            raised=_spaced(raised),
            target=_spaced(goal.target_rub),
        )
    ]
    if goal.description:
        lines.insert(1, html.escape(goal.description))
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
    if recent:
        lines.append("")
        for row_user, amount, anonymous in recent:
            who = "🙈" if anonymous else html.escape(display_name(row_user))
            lines.append(f"▪️ {who} — {amount} ₽")

    text = "\n".join(lines)
    markup = goal_screen_keyboard(lang, post_url=url)
    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")
    return True


@router.callback_query(F.data == "don:goal")
async def cb_goal(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
    if not await _goal_screen(callback.message, lang, edit=True):
        await callback.answer(t("goal.none", lang), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data == "don:share")
async def cb_share(callback: CallbackQuery, state: FSMContext) -> None:
    """Экран пересылки: готовая ссылка текстом плюс кнопка отправки."""
    await state.set_state(None)
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
        goal = await goals.active_goal(session)
        if goal is None:
            await callback.answer(t("goal.none", lang), show_alert=True)
            return
        raised = await goals.goal_progress(session, goal.id)
        url = await goal_post.post_url(goal)

    link = _goal_link()
    share_text = t("goal.share_text", lang).format(
        title=goal.title, percent=goals.progress_percent(raised, goal.target_rub)
    )
    # quote(safe="") обязателен: без него «&» и «=» из нашей ссылки станут
    # разделителями параметров самой шторки, и до друга уедет обрубок.
    share_url = (
        "https://t.me/share/url"
        f"?url={quote(link, safe='')}&text={quote(share_text, safe='')}"
    )
    await callback.message.edit_text(
        t("goal.share_screen", lang).format(link=html.escape(link)),
        reply_markup=goal_share_keyboard(share_url, lang, post_url=url),
        parse_mode="HTML",
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
    if method == "ton" and not _ton_available():
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
    # Сумму в TON показываем, только когда её есть чем посчитать: у Crypto Pay
    # курс свой и станет известен лишь на их экране оплаты.
    ton = ton_donations.ton_for_rub(amount) if ton_donations.is_configured() else None
    markup = donate_method_keyboard(amount, ton, lang)
    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


async def _start_ton_payment(
    message: Message, telegram_id: int, amount: int, lang: str, edit: bool, anonymous: bool
) -> None:
    """Оплата в TON. Путей два, и первым идёт тот, что удобнее человеку.

    Crypto Pay: счёт выставляется в рублях, человек платит в один тап в
    @CryptoBot, зачисление приходит вебхуком. Прямой перевод на кошелёк:
    ключей не нужно вовсе, но адрес и метку человек копирует сам.
    """
    if crypto_pay.is_configured():
        result = await crypto_pay.create_invoice(telegram_id, amount, anonymous=anonymous)
        if result is None:
            text, markup = t("donate.error", lang), donate_keyboard(lang, anonymous=anonymous)
        else:
            _invoice_id, link = result
            text = t("donate.pay_prompt", lang).format(amount=amount)
            markup = donate_pay_keyboard(link, lang)
    elif ton_donations.is_configured():
        ton = ton_donations.ton_for_rub(amount)
        memo = ton_donations.make_memo(telegram_id, anonymous=anonymous)
        text = t("donate.ton_manual", lang).format(
            amount=amount,
            ton=ton,
            address=html.escape(settings.ton_wallet_address),
            memo=html.escape(memo),
        )
        markup = ton_manual_keyboard(ton_donations.transfer_link(ton, memo), amount, lang)
    else:
        text, markup = t("donate.unavailable", lang), donate_keyboard(lang, anonymous=anonymous)

    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("don:tonok:"))
async def cb_ton_check(callback: CallbackQuery) -> None:
    """«Я перевёл» — разобрать свежие приходы прямо сейчас.

    Проверка по кнопке нужна не вместо фонового опроса, а вместе с ним: человек
    только что отправил перевод и хочет видеть результат сразу, а не ждать
    следующего прохода таймера.
    """
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        lang = user_language(user)
        before = await user_total(session, user.id)
        transactions = await ton_donations.fetch_incoming()
        if transactions is None:
            # ⚠️ «Спросить не удалось» и «денег нет» — разные вещи, и путать их
            # нельзя: человек, которому сказали «перевода не вижу» из-за сбоя
            # сети, решит, что деньги пропали.
            await callback.answer(t("donate.ton_unavailable", lang), show_alert=True)
            return
        await ton_donations.collect(session)
        after = await user_total(session, user.id)

    if after > before:
        await callback.answer(
            t("donate.ton_found", lang).format(amount=after - before), show_alert=True
        )
        await _show_donate_screen(callback.message, lang, edit=True)
        return
    await callback.answer(t("donate.ton_not_found", lang), show_alert=True)


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
    if method is None and _ton_available():
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


async def show_goal_from_start(message: Message, lang: str) -> None:
    """Экран сбора по deep-link `/start goal` — по этой ссылке сбор расходится
    по чатам и другим соцсетям.

    Сбор мог закончиться, пока ссылка ходила по рукам, поэтому человек не должен
    упереться в пустоту: показываем обычный экран поддержки.
    """
    if not await _goal_screen(message, lang, edit=False):
        await _show_donate_screen(message, lang, edit=False)
