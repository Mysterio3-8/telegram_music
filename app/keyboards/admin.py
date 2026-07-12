from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel_keyboard(reclaimable_count: int = 0) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:stats")]]
    if reclaimable_count > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🧹 Освободить диск ({reclaimable_count})",
                    callback_data="adm:reclaim:ask",
                )
            ]
        )
    rows += [
        [InlineKeyboardButton(text="➕ Загрузить минусы", callback_data="adm:upload_minus")],
        [InlineKeyboardButton(text="🎬 YouTube-источники", callback_data="adm:yt")],
        [InlineKeyboardButton(text="📡 Мой Telegram-канал", callback_data="adm:tgc")],
        [InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reclaim_confirm_keyboard(count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🧹 Да, удалить {count} файлов с диска", callback_data="adm:reclaim:go"
                )
            ],
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="adm:stats")],
        ]
    )
