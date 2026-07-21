"""Рассылка из админки (NEXT_SESSION P6): текст (+опц. фото) → предпросмотр →
подтверждение → Celery-задача broadcast.send с троттлингом и отчётом.

Хендлер только собирает контент и подтверждение — отправка идёт в воркере,
бот не блокируется на тысячах сообщений.
"""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import settings
from app.db.base import session_factory
from app.services.broadcast import active_recipient_ids
from app.services.users import is_admin

logger = logging.getLogger(__name__)

router = Router()


class Broadcast(StatesGroup):
    waiting_content = State()
    waiting_confirm = State()


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📣 Отправить всем", callback_data="adm:bcast:go")],
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="adm:bcast:cancel")],
        ]
    )


@router.callback_query(F.data == "adm:bcast")
async def cb_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    await state.set_state(Broadcast.waiting_content)
    await callback.message.answer(
        "📣 Рассылка всем пользователям.\n\n"
        "Пришлите текст сообщения — или фото с подписью."
    )
    await callback.answer()


@router.message(Broadcast.waiting_content, F.photo)
async def process_broadcast_photo(message: Message, state: FSMContext) -> None:
    await state.update_data(
        bcast_text=message.caption or "", bcast_photo=message.photo[-1].file_id
    )
    await _show_preview(message, state)


@router.message(Broadcast.waiting_content, F.text)
async def process_broadcast_text(message: Message, state: FSMContext) -> None:
    await state.update_data(bcast_text=message.text, bcast_photo=None)
    await _show_preview(message, state)


async def _show_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    async with session_factory() as session:
        recipients = len(await active_recipient_ids(session))
    await state.set_state(Broadcast.waiting_confirm)

    # Предпросмотр — то же сообщение, каким его увидят пользователи
    if data.get("bcast_photo"):
        await message.answer_photo(data["bcast_photo"], caption=data.get("bcast_text") or None)
    else:
        await message.answer(data.get("bcast_text") or "")
    await message.answer(
        f"Так сообщение увидят пользователи.\nПолучателей: {recipients}.\nОтправляем?",
        reply_markup=_confirm_keyboard(),
    )


@router.callback_query(F.data == "adm:bcast:cancel")
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Рассылка отменена.")
    await callback.answer()


@router.callback_query(F.data == "adm:bcast:go")
async def cb_broadcast_go(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    data = await state.get_data()
    text = data.get("bcast_text") or ""
    photo = data.get("bcast_photo")
    if not text and not photo:
        await callback.answer("Нет содержимого — начните заново", show_alert=True)
        await state.clear()
        return

    if not settings.effective_celery_broker:
        await callback.answer()
        await callback.message.edit_text(
            "Рассылка недоступна: не настроен брокер фоновых задач (Redis/Celery)."
        )
        await state.clear()
        return

    from app.tasks.broadcast import send_broadcast

    try:
        send_broadcast.delay(text, photo, callback.from_user.id)
    except Exception:  # noqa: BLE001 — брокер лежит: честный отказ вместо тихой потери
        logger.exception("Рассылка: не удалось поставить задачу")
        await callback.answer()
        await callback.message.edit_text("Не удалось запустить рассылку — брокер недоступен.")
        await state.clear()
        return

    await state.clear()
    await callback.message.edit_text(
        "📣 Рассылка запущена. По завершении пришлю отчёт "
        "(доставлено / заблокировали бота / ошибки)."
    )
    await callback.answer()
