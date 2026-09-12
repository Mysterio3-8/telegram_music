from aiogram.types import Message, TelegramObject


def is_payment_message(event: TelegramObject) -> bool:
    """Служебное сообщение о платеже: оплата прошла или деньги вернулись.

    🔴 Такое сообщение не гасит ни гейт подписки, ни антифлуд. Его шлёт не
    человек, а Telegram, и шлёт ровно один раз: деньги к этому моменту уже
    списаны. Погаси его мидлварь (отписался от канала между счётом и оплатой,
    попал под паузу антифлуда) — и списание остаётся без Premium и без доната,
    а повторно Telegram его не пришлёт.
    """
    return isinstance(event, Message) and (
        event.successful_payment is not None or event.refunded_payment is not None
    )
