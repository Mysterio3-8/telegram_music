"""Админка целей сбора: завести, опубликовать в канале, обновить, закрыть.

Отдельным модулем от [admin.py](app/handlers/admin.py) — как admin_youtube и
admin_upload_minus: у раздела свой мастер на пять шагов, и в общем файле он
утонул бы.

Инвариант проекта соблюдён: здесь роутинг и текст, вся работа с целями — в
[donation_goals.py](app/services/donation_goals.py) и
[goal_post.py](app/services/goal_post.py).

⚠️ Админка не переведена сознательно — как и остальная админка проекта: её
видят два русскоязычных человека.
"""
import html
import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.db.base import session_factory
from app.services import donation_goals as goals
from app.services import goal_post
from app.services.users import is_admin

router = Router()
logger = logging.getLogger(__name__)

# «-» как «пропустить» вместо отдельной кнопки: мастер идёт текстом, и лишняя
# клавиатура на каждом шаге дороже одного понятного символа.
SKIP = {"-", "—", "нет", "пропустить"}

MAX_TITLE = 128
MAX_DESCRIPTION = 1024
MIN_TARGET = 100
MAX_TARGET = 100_000_000
MAX_DAYS = 365


class GoalCreate(StatesGroup):
    waiting_title = State()
    waiting_target = State()
    waiting_description = State()
    waiting_image = State()
    waiting_days = State()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _spaced(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def _panel_keyboard(
    has_goal: bool, published: bool, *, can_reopen: bool = False
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_goal:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔁 Обновить пост" if published else "📢 Опубликовать в канале",
                    callback_data="adm:goal:refresh" if published else "adm:goal:pub",
                )
            ]
        )
        if published:
            rows.append(
                [InlineKeyboardButton(text="📢 Опубликовать заново", callback_data="adm:goal:pub")]
            )
        rows.append(
            [InlineKeyboardButton(text="🏁 Закрыть цель", callback_data="adm:goal:close:ask")]
        )
    else:
        rows.append([InlineKeyboardButton(text="➕ Завести цель", callback_data="adm:goal:new")])
        # Закрыть цель легко случайно — кнопка в двух тапах отсюда, и владелец
        # так и сделал 10.09. Поэтому рядом стоит возврат последней закрытой: он
        # ничего не восстанавливает из небытия, лишь снимает пометку «закрыта».
        if can_reopen:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="↩️ Вернуть прошлую цель", callback_data="adm:goal:reopen"
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm:stats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _panel_text(session) -> tuple[str, bool, bool]:
    goal = await goals.active_goal(session)
    if goal is None:
        text = (
            "🎯 <b>Цели сбора</b>\n\n"
            "Активной цели нет. Пока её нет, донаты просто идут в общий зачёт "
            "и в рейтинг спонсоров.\n\n"
            "Заведите цель — и у неё появятся прогресс-бар в боте и пост в канале, "
            "который бот сам перерисовывает после каждого доната."
        )
        return text, False, False

    raised = await goals.goal_progress(session, goal.id)
    lines = [
        "🎯 <b>Цели сбора</b>",
        "",
        f"<b>{html.escape(goal.title)}</b>",
        f"<code>{goals.progress_bar(raised, goal.target_rub)}</code> "
        f"{goals.progress_percent(raised, goal.target_rub)}%",
        f"Собрано {_spaced(raised)} из {_spaced(goal.target_rub)} ₽",
    ]
    left = goals.days_left(goal)
    if left is not None:
        lines.append(f"Срок: {'осталось дней ' + str(left) if left >= 0 else 'вышел'}")
    if goal.reached_at:
        lines.append("✅ Цель достигнута")
    if goal.channel_message_id:
        lines.append(f"Пост: опубликован (чат {goal.channel_chat_id})")
    else:
        channel = settings.effective_goal_channel_id
        lines.append(
            "Пост: не опубликован"
            if channel
            else "Пост: не опубликован, и канал не задан — впишите GOAL_CHANNEL_ID в .env"
        )
    recent = await goals.recent_donations(session, goal.id)
    if recent:
        lines.append("")
        lines.append("<b>Последние донаты:</b>")
        for user, amount, anonymous in recent:
            who = "Аноним" if anonymous else html.escape(user.username or f"#{user.id}")
            lines.append(f"▪️ {who} — {amount} ₽")
    return "\n".join(lines), True, bool(goal.channel_message_id)


async def _show_panel(message: Message, edit: bool) -> None:
    async with session_factory() as session:
        text, has_goal, published = await _panel_text(session)
        # Есть ли что возвращать — спрашиваем, только когда активной цели нет:
        # иначе кнопка всё равно не показывается, а запрос был бы впустую.
        can_reopen = not has_goal and await goals.has_closed_goal(session)
    markup = _panel_keyboard(has_goal, published, can_reopen=can_reopen)
    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "adm:goal")
async def cb_panel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    await state.set_state(None)
    await _show_panel(callback.message, edit=True)
    await callback.answer()


# --- мастер создания --------------------------------------------------------


@router.callback_query(F.data == "adm:goal:new")
async def cb_new(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    await state.set_state(GoalCreate.waiting_title)
    await callback.message.edit_text(
        "🎯 <b>Новая цель</b>\n\nШаг 1 из 5. Напишите название — коротко, "
        "как заголовок поста.\n\n<i>Например: Новый сервер</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(GoalCreate.waiting_title, F.text)
async def step_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title or len(title) > MAX_TITLE:
        await message.answer(f"Название нужно от 1 до {MAX_TITLE} символов. Попробуйте ещё раз.")
        return
    await state.update_data(title=title)
    await state.set_state(GoalCreate.waiting_target)
    await message.answer(
        "Шаг 2 из 5. Сколько собрать? Целое число рублей.\n\n<i>Например: 30000</i>",
        parse_mode="HTML",
    )


@router.message(GoalCreate.waiting_target, F.text)
async def step_target(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(" ", "").replace("_", "")
    # isascii рядом с isdigit обязателен: «²» проходит isdigit(), но int() падает.
    if not (raw.isascii() and raw.isdigit()):
        await message.answer("Нужно целое число, только цифры. Например: 30000")
        return
    target = int(raw)
    if not (MIN_TARGET <= target <= MAX_TARGET):
        await message.answer(f"Сумма должна быть от {MIN_TARGET} до {_spaced(MAX_TARGET)} ₽.")
        return
    await state.update_data(target=target)
    await state.set_state(GoalCreate.waiting_description)
    await message.answer(
        "Шаг 3 из 5. Опишите, на что собираем — пара предложений.\n\n"
        "<i>Или отправьте «-», чтобы пропустить.</i>",
        parse_mode="HTML",
    )


@router.message(GoalCreate.waiting_description, F.text)
async def step_description(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    description = None if raw.lower() in SKIP else raw[:MAX_DESCRIPTION]
    await state.update_data(description=description)
    await state.set_state(GoalCreate.waiting_image)
    await message.answer(
        "Шаг 4 из 5. Пришлите картинку для поста.\n\n"
        "<i>Или «-», чтобы пост был без картинки. ⚠️ У поста с картинкой "
        "текста помещается меньше — Telegram ограничивает подпись 1024 символами.</i>",
        parse_mode="HTML",
    )


@router.message(GoalCreate.waiting_image, F.photo)
async def step_image_photo(message: Message, state: FSMContext) -> None:
    # Берём последний размер — он самый крупный.
    await state.update_data(image_file_id=message.photo[-1].file_id)
    await state.set_state(GoalCreate.waiting_days)
    await message.answer(
        "Шаг 5 из 5. Срок сбора в днях.\n\n<i>Или «-», если без срока.</i>",
        parse_mode="HTML",
    )


@router.message(GoalCreate.waiting_image, F.text)
async def step_image_skip(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip().lower() not in SKIP:
        await message.answer("Пришлите картинку или «-», чтобы пропустить.")
        return
    await state.update_data(image_file_id=None)
    await state.set_state(GoalCreate.waiting_days)
    await message.answer(
        "Шаг 5 из 5. Срок сбора в днях.\n\n<i>Или «-», если без срока.</i>",
        parse_mode="HTML",
    )


@router.message(GoalCreate.waiting_days, F.text)
async def step_days(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    deadline = None
    if raw.lower() not in SKIP:
        if not (raw.isascii() and raw.isdigit()) or not (1 <= int(raw) <= MAX_DAYS):
            await message.answer(f"Нужно число дней от 1 до {MAX_DAYS} или «-».")
            return
        deadline = _utcnow() + timedelta(days=int(raw))

    data = await state.get_data()
    await state.set_state(None)
    async with session_factory() as session:
        goal = await goals.create_goal(
            session,
            title=data["title"],
            target_rub=data["target"],
            description=data.get("description"),
            image_file_id=data.get("image_file_id"),
            deadline=deadline,
        )
    if goal is None:
        # Между началом мастера и его концом цель мог завести второй админ.
        await message.answer("Активная цель уже есть — сначала закройте её.")
        await _show_panel(message, edit=False)
        return

    await message.answer(f"✅ Цель «{html.escape(goal.title)}» заведена.", parse_mode="HTML")
    await _show_panel(message, edit=False)


# --- публикация и закрытие --------------------------------------------------


@router.callback_query(F.data == "adm:goal:reopen")
async def cb_reopen(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    async with session_factory() as session:
        goal = await goals.reopen_goal(session)
        if goal is None:
            await callback.answer("Вернуть нечего", show_alert=True)
            return
        # Пост в канале пережил закрытие — перерисовываем сразу, чтобы
        # подписчики увидели живой сбор, а не замерший.
        await goal_post.refresh(session, goal)
    await _show_panel(callback.message, edit=True)
    await callback.answer("Цель снова в работе")


@router.callback_query(F.data == "adm:goal:pub")
async def cb_publish(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    chat_id = settings.effective_goal_channel_id
    if not chat_id:
        await callback.answer(
            "Канал не задан. Впишите GOAL_CHANNEL_ID в .env на сервере.", show_alert=True
        )
        return
    async with session_factory() as session:
        goal = await goals.active_goal(session)
        if goal is None:
            await callback.answer("Активной цели нет", show_alert=True)
            return
        ok = await goal_post.publish(session, goal, chat_id)
    if not ok:
        await callback.answer(
            "Не получилось. Чаще всего причина одна: бот не администратор канала.",
            show_alert=True,
        )
        return
    await _show_panel(callback.message, edit=True)
    await callback.answer("Опубликовано")


@router.callback_query(F.data == "adm:goal:refresh")
async def cb_refresh(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    async with session_factory() as session:
        ok = await goal_post.refresh_active(session)
    # «Не изменилось» Telegram считает ошибкой, а для нас это норма: с прошлой
    # правки могло не прийти ни одного доната.
    await callback.answer("Пост обновлён" if ok else "Пост уже актуален либо Telegram отказал")


@router.callback_query(F.data == "adm:goal:close:ask")
async def cb_close_ask(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    async with session_factory() as session:
        goal = await goals.active_goal(session)
        if goal is None:
            await callback.answer("Активной цели нет", show_alert=True)
            return
        raised = await goals.goal_progress(session, goal.id)
    await callback.message.edit_text(
        f"🏁 Закрыть цель «{html.escape(goal.title)}»?\n\n"
        f"Собрано {_spaced(raised)} из {_spaced(goal.target_rub)} ₽.\n\n"
        "Донаты никуда не денутся — они останутся в истории и в общем рейтинге. "
        "Пост в канале перестанет обновляться, после чего можно завести следующую цель.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏁 Да, закрыть", callback_data="adm:goal:close:go")],
                [InlineKeyboardButton(text="◀️ Отмена", callback_data="adm:goal")],
            ]
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "adm:goal:close:go")
async def cb_close_go(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    async with session_factory() as session:
        goal = await goals.active_goal(session)
        if goal is None:
            await callback.answer("Активной цели нет", show_alert=True)
            return
        # Последняя правка поста перед закрытием: в канале должна остаться
        # итоговая сумма, а не та, что была на предпоследнем донате.
        await goal_post.refresh(session, goal)
        await goals.close_goal(session, goal)
    await _show_panel(callback.message, edit=True)
    await callback.answer("Цель закрыта")
