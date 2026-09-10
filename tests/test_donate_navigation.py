"""Навигация по экранам доната.

Владелец жаловался дважды: «жму назад — возвращает на главную» и «слишком много
кнопок, водят по кругу». Оба раза причина была в разметке, а не в логике,
поэтому проверяем именно разметку — какие кнопки есть на экране и куда ведут.

Два правила, которые здесь стерегутся:

1. **Ни одна пара кнопок на экране не ведёт в одно и то же место.** Именно такие
   двойники и создавали ощущение хождения по кругу.
2. **«Назад» возвращает туда, откуда пришли**, а не в заранее выбранную точку.
"""
import pytest

from app.keyboards.donate import (
    donate_cancel_keyboard,
    donate_keyboard,
    donate_method_keyboard,
    donate_top_keyboard,
    goal_screen_keyboard,
    goal_share_keyboard,
)


def _targets(markup) -> list[str]:
    """Куда ведут кнопки: callback_data либо «url:…» для ссылок."""
    out = []
    for row in markup.inline_keyboard:
        for button in row:
            out.append(button.callback_data or f"url:{button.url}")
    return out


def _back(markup) -> str | None:
    """Адрес последней кнопки — по разметке проекта это всегда «Назад»."""
    return _targets(markup)[-1]


ALL_SCREENS = [
    ("экран поддержки без сбора", donate_keyboard("ru", has_goal=False)),
    ("экран поддержки со сбором", donate_keyboard("ru", has_goal=True)),
    ("выбор способа оплаты", donate_method_keyboard(100, 0.33, "ru")),
    ("ввод своей суммы", donate_cancel_keyboard("ru")),
    ("рейтинг за всё время", donate_top_keyboard("ru", showing_goal=False, has_goal=True)),
    ("рейтинг по цели", donate_top_keyboard("ru", showing_goal=True, has_goal=True)),
    ("экран сбора", goal_screen_keyboard("ru")),
    ("экран сбора с постом", goal_screen_keyboard("ru", post_url="https://t.me/c/1")),
    ("экран шаринга", goal_share_keyboard("https://t.me/share/url?url=x", "ru")),
]


@pytest.mark.parametrize("name,markup", ALL_SCREENS, ids=[s[0] for s in ALL_SCREENS])
def test_no_two_buttons_lead_to_the_same_place(name, markup):
    """🔴 Жалоба владельца «кнопки водят по кругу».

    Двойники были на экране сбора («Поддержать сбор» и «Назад» вели на экран
    поддержки) и на рейтинге. Человек жал разные кнопки и попадал в одно место —
    отсюда ощущение, что из раздела не выбраться.
    """
    targets = _targets(markup)
    duplicates = {x for x in targets if targets.count(x) > 1}
    assert not duplicates, f"{name}: кнопки-двойники ведут в {duplicates}"


@pytest.mark.parametrize("name,markup", ALL_SCREENS, ids=[s[0] for s in ALL_SCREENS])
def test_every_screen_has_a_way_back(name, markup):
    """Из любого экрана раздела должен быть выход — тупик хуже лишней кнопки."""
    assert _targets(markup), f"{name}: пустая клавиатура"
    assert _back(markup).startswith(("don:", "menu:")), f"{name}: последняя кнопка не ведёт назад"


def test_back_from_goal_rating_returns_to_goal():
    """🔴 Ровно та жалоба: «жму донаты → по текущей цели → назад, а попадаю в
    главное меню». Пришли со сбора — вернуться обязаны на сбор."""
    markup = donate_top_keyboard("ru", showing_goal=True, has_goal=True, origin="g")
    assert _back(markup) == "don:goal"


def test_back_from_rating_returns_to_support_when_opened_there():
    markup = donate_top_keyboard("ru", showing_goal=True, has_goal=True, origin="o")
    assert _back(markup) == "don:open"


def test_rating_switch_keeps_the_origin():
    """Переключение «по цели ↔ за всё время» не должно терять, откуда пришли:
    иначе один переключатель — и «Назад» снова уводит не туда."""
    markup = donate_top_keyboard("ru", showing_goal=True, has_goal=True, origin="g")
    assert "don:top:g" in _targets(markup)

    markup = donate_top_keyboard("ru", showing_goal=False, has_goal=True, origin="g")
    assert "don:goaltop:g" in _targets(markup)


def test_support_screen_goes_back_to_main_menu():
    """А вот отсюда «Назад» в меню — это и есть «откуда пришли»."""
    assert _back(donate_keyboard("ru")) == "menu:main"


def test_goal_screen_goes_back_to_support():
    assert _back(goal_screen_keyboard("ru")) == "don:open"


def test_share_screen_goes_back_to_goal():
    assert _back(goal_share_keyboard("https://t.me/share/url?url=x", "ru")) == "don:goal"


# --- количество кнопок ------------------------------------------------------

@pytest.mark.parametrize("name,markup", ALL_SCREENS, ids=[s[0] for s in ALL_SCREENS])
def test_screens_stay_compact(name, markup):
    """Вторая жалоба — «слишком много кнопок».

    Семь рядов это уже предел читаемого экрана на телефоне: дальше список
    приходится листать, и человек перестаёт видеть его целиком.
    """
    assert len(markup.inline_keyboard) <= 7, f"{name}: {len(markup.inline_keyboard)} рядов"


def test_rating_is_not_duplicated_next_to_the_goal():
    """Когда сбор идёт, общий рейтинг уходит внутрь сбора.

    Иначе на одном экране стояли «Текущий сбор», «Рейтинг спонсоров» и «По
    текущей цели» — три кнопки про почти одно и то же.
    """
    targets = _targets(donate_keyboard("ru", has_goal=True))
    assert "don:goal" in targets
    assert not [x for x in targets if x.startswith("don:top")]

    # Без сбора рейтинг обязан остаться доступным напрямую.
    targets = _targets(donate_keyboard("ru", has_goal=False))
    assert "don:top:o" in targets
