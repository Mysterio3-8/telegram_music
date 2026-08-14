"""Где именно произошло событие: личка или общий чат.

Вынесено отдельным модулем, потому что нужно в трёх мидлварях и в хендлерах, а
дублировать разбор `chat.type` в каждом месте — верный способ однажды забыть
про группы в одном из них и получить там неверное поведение.

Что меняется в группе (пункт 6 спеки 13.08):

- **гейт обязательной подписки не применяется.** Проверять в общем чате нечего:
  бот отвечает всем участникам сразу, и требовать подписку у каждого — значит
  сделать его немым. Плюс `is_fully_subscribed` работает fail-closed, то есть
  при первой же ошибке Telegram API бот в группе просто замолчал бы;
- **реклама не показывается.** Сообщение «купи Premium» в чужом чате это спам от
  нашего имени, за который выгоняют бота, а не покупают подписку;
- **диалоговые мастера не запускаются.** Загрузка трека спрашивает название,
  потом исполнителя; в общем чате следующее сообщение придёт от другого человека,
  и мастер соберёт из двух собеседников одну кашу;
- **антифлуд считает ещё и по чату.** Лимиты по пользователю в группе бесполезны:
  десять человек по одному действию каждый — это десять действий, и каждый в
  своём праве.
"""
from aiogram.types import Chat, TelegramObject

PRIVATE = "private"
GROUP_TYPES = frozenset({"group", "supergroup"})


def event_chat(event: TelegramObject, data: dict | None = None) -> Chat | None:
    """Чат события. aiogram кладёт его в data['event_chat'] — оттуда и берём,
    а для прямых вызовов из хендлеров разбираем сам объект."""
    if data is not None and data.get("event_chat") is not None:
        return data["event_chat"]
    chat = getattr(event, "chat", None)
    if chat is not None:
        return chat
    message = getattr(event, "message", None)  # CallbackQuery
    return getattr(message, "chat", None)


def is_private(event: TelegramObject, data: dict | None = None) -> bool:
    """True — личка с ботом. Неизвестный чат считаем личкой: так ведёт себя
    весь прежний код, и менять поведение там, где мы не уверены, опаснее."""
    chat = event_chat(event, data)
    return chat is None or chat.type == PRIVATE


def is_group(event: TelegramObject, data: dict | None = None) -> bool:
    chat = event_chat(event, data)
    return chat is not None and chat.type in GROUP_TYPES
