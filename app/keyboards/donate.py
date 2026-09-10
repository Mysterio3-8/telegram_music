"""Разметка экранов доната. Только кнопки, без логики."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.i18n import DEFAULT_LANGUAGE, t
from app.services.donations import DONATE_PRESETS


def donate_keyboard(
    lang: str = DEFAULT_LANGUAGE, *, anonymous: bool = False, has_goal: bool = False
) -> InlineKeyboardMarkup:
    """Суммы по две в ряд, тумблер анонимности, рейтинг, правила и назад."""
    amounts = [
        InlineKeyboardButton(text=f"{amount} ₽", callback_data=f"don:pay:{amount}")
        for amount in DONATE_PRESETS
    ]
    rows: list[list[InlineKeyboardButton]] = [
        amounts[i : i + 2] for i in range(0, len(amounts), 2)
    ]
    rows.append(
        [InlineKeyboardButton(text=t("donate.custom", lang), callback_data="don:custom")]
    )
    # Тумблер стоит ВЫШЕ кнопок оплаты по смыслу, но ниже по месту: выбор суммы —
    # главное действие экрана, и отодвигать его вниз ради настройки нельзя.
    anon_key = "donate.anon_on" if anonymous else "donate.anon_off"
    rows.append([InlineKeyboardButton(text=t(anon_key, lang), callback_data="don:anon")])
    # Кнопка вклада в цель появляется только когда сбор идёт — иначе она вела бы
    # на пустой экран.
    # ⚠️ Когда сбор идёт, общий рейтинг УБИРАЕТСЯ с этого экрана и живёт внутри
    # сбора. Иначе на одном экране оказывались и «Текущий сбор», и «Рейтинг», и
    # «По текущей цели» — три кнопки про почти одно и то же, между которыми
    # человек ходил кругами (жалоба владельца 09.09).
    if has_goal:
        rows.append([InlineKeyboardButton(text=t("goal.open", lang), callback_data="don:goal")])
    else:
        rows.append(
            [InlineKeyboardButton(text=t("donate.top", lang), callback_data="don:top:o")]
        )
    # Полные правила живут вне бота (решение владельца). Пока ссылка не задана —
    # кнопки нет: мёртвая кнопка хуже отсутствующей. Короткая версия правил всё
    # равно всегда на экране.
    if settings.donate_rules_url:
        rows.append(
            [InlineKeyboardButton(text=t("donate.rules", lang), url=settings.donate_rules_url)]
        )
    rows.append([InlineKeyboardButton(text=t("donate.back", lang), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def donate_pay_keyboard(url: str, lang: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Ссылка на кассу плюс возврат к выбору суммы."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("donate.pay", lang), url=url)],
            [InlineKeyboardButton(text=t("donate.back", lang), callback_data="don:open")],
        ]
    )


def donate_top_keyboard(
    lang: str = DEFAULT_LANGUAGE,
    *,
    showing_goal: bool = False,
    has_goal: bool = False,
    origin: str = "o",
) -> InlineKeyboardMarkup:
    """С рейтинга — назад к выбору суммы, а не в главное меню: человек пришёл
    поддержать, и терять его на экране со списком незачем.

    Плюс переключатель между двумя рейтингами. Кнопка всегда называет ТО, КУДА
    ведёт, а не то, что открыто сейчас: подпись «за всё время» на экране «за всё
    время» читалась бы как заголовок, и по ней бы не нажимали.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if showing_goal:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("goal.switch_all", lang), callback_data=f"don:top:{origin}"
                )
            ]
        )
    elif has_goal:
        rows.append(
            [
                InlineKeyboardButton(
                    text=t("goal.switch_goal", lang), callback_data=f"don:goaltop:{origin}"
                )
            ]
        )
    # ⚠️ «Назад» возвращает ТУДА, ОТКУДА пришли, а не в заранее выбранное место.
    # Откуда именно — едет в callback_data: «g» — экран сбора, «o» — экран
    # поддержки. Захардкоженный адрес и был жалобой владельца: человек заходил
    # в рейтинг из сбора, а выходил в другое место.
    back = "don:goal" if origin == "g" else "don:open"
    rows.append([InlineKeyboardButton(text=t("donate.back", lang), callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def donate_cancel_keyboard(lang: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Отмена ввода своей суммы."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("donate.back", lang), callback_data="don:open")]
        ]
    )


def donate_method_keyboard(
    amount: int, ton_amount: float | None = None, lang: str = DEFAULT_LANGUAGE
) -> InlineKeyboardMarkup:
    """Выбор способа: рубли или TON.

    Показывается ТОЛЬКО когда TON действительно доступен. Иначе экран с одной
    кнопкой был бы лишним шагом между человеком и оплатой.

    `ton_amount=None` — курс нам неизвестен (так у Crypto Pay: он считает свой
    курс на своём экране оплаты). Тогда на кнопке просто «TON» без числа: лучше
    не показать сумму, чем показать выдуманную.
    """
    ton_text = t("donate.pay_ton", lang).format(ton=ton_amount) if ton_amount else "💎 TON"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("donate.pay_rub", lang), callback_data=f"don:rub:{amount}"
                )
            ],
            [InlineKeyboardButton(text=ton_text, callback_data=f"don:ton:{amount}")],
            [InlineKeyboardButton(text=t("donate.back", lang), callback_data="don:open")],
        ]
    )


def ton_manual_keyboard(
    wallet_url: str, amount: int, lang: str = DEFAULT_LANGUAGE
) -> InlineKeyboardMarkup:
    """Прямой перевод на кошелёк: открыть кошелёк, проверить, назад."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("donate.ton_open_wallet", lang), url=wallet_url)],
            [
                InlineKeyboardButton(
                    text=t("donate.ton_check", lang), callback_data=f"don:tonok:{amount}"
                )
            ],
            [InlineKeyboardButton(text=t("donate.back", lang), callback_data="don:open")],
        ]
    )


def goal_screen_keyboard(
    lang: str = DEFAULT_LANGUAGE, *, post_url: str | None = None
) -> InlineKeyboardMarkup:
    """Экран сбора: поддержать, поделиться, пост в канале, вклад, назад."""
    # ⚠️ Кнопки «Поддержать сбор» здесь больше нет: она вела ровно туда же, куда
    # «Назад» (на экран поддержки), и из-за этой пары экран замыкался сам на
    # себя. Одно действие — одна кнопка.
    rows = [[InlineKeyboardButton(text=t("goal.share", lang), callback_data="don:share")]]
    # Кнопки на пост нет, пока сбор не опубликован: мёртвая ссылка хуже её
    # отсутствия.
    if post_url:
        rows.append([InlineKeyboardButton(text=t("goal.post_link", lang), url=post_url)])
    rows.append(
        [InlineKeyboardButton(text=t("donate.top", lang), callback_data="don:goaltop:g")]
    )
    rows.append([InlineKeyboardButton(text=t("donate.back", lang), callback_data="don:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def goal_share_keyboard(share_url: str, lang: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
    """Пересылка сбора.

    `t.me/share/url` открывает штатную шторку выбора чата — работает у всех и
    не требует включённого инлайн-режима (он у бота до сих пор не включён у
    BotFather, и кнопка на нём молча ничего бы не делала).
    """
    # Ссылки на пост здесь нет намеренно: она уже есть на экране сбора, откуда
    # сюда и попадают. Повторять её — снова разводить кнопки-двойники.
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("goal.share_send", lang), url=share_url)],
            [InlineKeyboardButton(text=t("donate.back", lang), callback_data="don:goal")],
        ]
    )
