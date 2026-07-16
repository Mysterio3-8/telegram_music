from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel_keyboard(reclaimable_count: int = 0, junk_count: int = 0) -> InlineKeyboardMarkup:
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
    if junk_count > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 Не-музыка ({junk_count})",
                    callback_data="adm:junk:ask",
                )
            ]
        )
    rows += [
        [InlineKeyboardButton(text="📢 Каналы подписки", callback_data="adm:subch")],
        [InlineKeyboardButton(text="➕ Загрузить минусы", callback_data="adm:upload_minus")],
        [InlineKeyboardButton(text="🎬 YouTube-источники", callback_data="adm:yt")],
        [InlineKeyboardButton(text="📡 Мой Telegram-канал", callback_data="adm:tgc")],
        [InlineKeyboardButton(text="◀️ В меню", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sub_channels_keyboard(channels) -> InlineKeyboardMarkup:
    """channels: list[RequiredChannel] — по кнопке удаления на канал."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"🗑 {row.label} ({row.channel})", callback_data=f"adm:subch:del:{row.id}"
            )
        ]
        for row in channels
    ]
    rows += [
        [InlineKeyboardButton(text="➕ Добавить канал", callback_data="adm:subch:add")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:stats")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def junk_confirm_keyboard(count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🗑 Да, удалить {count} треков навсегда", callback_data="adm:junk:go"
                )
            ],
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="adm:stats")],
        ]
    )


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
