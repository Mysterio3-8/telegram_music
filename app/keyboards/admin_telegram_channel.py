from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import TelegramChannelSource


def sources_keyboard(
    sources: list[TelegramChannelSource], importer_enabled: bool
) -> InlineKeyboardMarkup:
    power_text = "🔴 Выключить импортёр" if importer_enabled else "🟢 Включить импортёр"
    rows = [[InlineKeyboardButton(text=power_text, callback_data="adm:tgc:power")]]
    rows += [
        [
            InlineKeyboardButton(
                text=f"{'🟢' if s.status == 'active' else '⏸'} #{s.id} · {s.imported_count}/{s.found_count}",
                callback_data=f"adm:tgcs:{s.id}",
            )
        ]
        for s in sources
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="adm:tgc:add")])
    rows.append([InlineKeyboardButton(text="◀️ В админку", callback_data="adm:stats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def source_view_keyboard(source: TelegramChannelSource) -> InlineKeyboardMarkup:
    toggle_text = "⏸ Отключить" if source.status == "active" else "🟢 Включить"
    rows = [
        [InlineKeyboardButton(text="🔄 Проверить сейчас", callback_data=f"adm:tgc:scan:{source.id}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"adm:tgc:tgl:{source.id}")],
        [InlineKeyboardButton(text="🗑 Удалить источник", callback_data=f"adm:tgc:delask:{source.id}")],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="adm:tgc")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_keyboard(source_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"adm:tgc:del:{source_id}")],
            [InlineKeyboardButton(text="◀️ Отмена", callback_data=f"adm:tgcs:{source_id}")],
        ]
    )
