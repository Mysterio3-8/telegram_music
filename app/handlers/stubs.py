from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router()

STUB_TEXTS = {
    "menu:premium": "💎 Premium появится на Этапе 3.",
    "menu:miniapp": "Mini App находится в разработке.",
}


@router.callback_query(F.data.in_(set(STUB_TEXTS)))
async def cb_stub(callback: CallbackQuery) -> None:
    await callback.answer(STUB_TEXTS[callback.data], show_alert=True)
