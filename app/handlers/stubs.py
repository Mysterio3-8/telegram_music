from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router()

STUB_TEXTS = {
    "menu:search": "🔍 Поиск по общей базе появится на Этапе 2.",
    "menu:playlists": "📂 Плейлисты появятся на Этапе 2.",
    "menu:instrumentals": "🎼 Поиск минусов появится на Этапе 2.",
    "menu:upload": "⬆️ Загрузка треков появится на Этапе 2.",
    "menu:premium": "💎 Premium появится на Этапе 3.",
    "menu:miniapp": "Mini App находится в разработке.",
    "stub:playlists": "📂 Плейлисты появятся на Этапе 2.",
    "stub:share": "📤 Поделиться появится на Этапе 2.",
}


@router.callback_query(F.data.in_(set(STUB_TEXTS)))
async def cb_stub(callback: CallbackQuery) -> None:
    await callback.answer(STUB_TEXTS[callback.data], show_alert=True)
