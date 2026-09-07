"""Запуск бота не должен превращаться в петлю рестартов.

Два разных отказа на старте, и путать их нельзя:
  • Telegram моргнул (сеть, 429, 500) — это временно. Меню команд украшение,
    бот работоспособен без него; падать тут значит менять работающего бота на
    подпись в меню, а `Restart=always` превращает это в круглосуточную петлю:
    каждый заход — полный импорт Python с aiogram, четверть единственного ядра.
  • Токен отозван — само не пройдёт. Повторять попытки бессмысленно, нужен код
    выхода, по которому systemd прекращает подъём (16.08: tg-music-moved так
    крутился 511 раз подряд).
"""
import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramUnauthorizedError
from aiogram.types import BotCommand, BotCommandScopeDefault

from app import bot_commands


class _FakeBot:
    """Бот, который валит set_my_commands заданным исключением."""

    def __init__(self, error=None):
        self.error = error
        self.calls = 0

    async def set_my_commands(self, commands, scope=None):
        self.calls += 1
        if self.error is not None:
            raise self.error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        TelegramNetworkError(method=None, message="сеть моргнула"),
        TelegramRetryAfter(method=None, message="слишком часто", retry_after=30),
    ],
)
async def test_transient_api_failure_does_not_stop_startup(error, monkeypatch):
    monkeypatch.setattr(bot_commands.settings, "admin_ids", "1,2")
    bot = _FakeBot(error)
    # Не должно поднять исключение: бот стартует без меню команд.
    await bot_commands.setup_bot_commands(bot)
    # И перебор не прекращается на первом отказе — админам тоже попробовали.
    assert bot.calls == 4, "по вызову на default, группы и каждого из двух админов"


@pytest.mark.asyncio
async def test_revoked_token_is_not_swallowed(monkeypatch):
    """Unauthorized — подкласс TelegramAPIError, и раньше он молча уходил в warning."""
    monkeypatch.setattr(bot_commands.settings, "admin_ids", "")
    bot = _FakeBot(TelegramUnauthorizedError(method=None, message="Unauthorized"))
    with pytest.raises(TelegramUnauthorizedError):
        await bot_commands.setup_bot_commands(bot)


@pytest.mark.asyncio
async def test_commands_are_set_when_telegram_is_healthy(monkeypatch):
    monkeypatch.setattr(bot_commands.settings, "admin_ids", "42")
    bot = _FakeBot()
    await bot_commands.setup_bot_commands(bot)
    assert bot.calls == 3


def test_empty_token_returns_config_exit_code(monkeypatch):
    """Пустой токен — отказ конфигурации, а не повод падать в петлю."""
    import asyncio

    from app import main as app_main

    monkeypatch.setattr(app_main.settings, "bot_token", "")
    assert asyncio.run(app_main.main()) == app_main.EXIT_BAD_TOKEN
    # 78 = EX_CONFIG; юнит гасит перезапуск по RestartPreventExitStatus.
    assert app_main.EXIT_BAD_TOKEN == 78


def test_unit_file_guards_against_restart_storm():
    """Юнит главного бота должен иметь те же рубежи, что воркеры и moved_bot."""
    import pathlib

    unit = pathlib.Path("deploy/tg-music-bot.service").read_text()
    # ⚠️ StartLimit* обязаны быть в [Unit]: в [Service] systemd их не читает.
    head = unit.split("\n[Service]")[0]
    assert "StartLimitBurst=5" in head
    assert "StartLimitIntervalSec=300" in head
    assert "RestartPreventExitStatus=78" in unit


def test_revoked_token_makes_main_exit_with_config_code(monkeypatch):
    """Unauthorized на старте → код 78, а не исключение и не бесконечная петля.

    Живьём это не проверить из песочницы (нет выхода к api.telegram.org), поэтому
    отказ подставляется на первом же обращении к Telegram — выставлении команд.
    """
    import asyncio

    from app import main as app_main

    monkeypatch.setattr(app_main.settings, "bot_token", "123456:TEST")
    # Без Redis: хранилище уйдёт в память, старт не зависит от внешнего сервиса.
    monkeypatch.setattr(app_main.settings, "redis_url", "")

    async def revoked(_bot):
        raise TelegramUnauthorizedError(method=None, message="Unauthorized")

    monkeypatch.setattr(app_main, "setup_bot_commands", revoked)

    polled = []

    async def never_polls(*args, **kwargs):
        polled.append(1)

    monkeypatch.setattr(app_main.Dispatcher, "start_polling", never_polls)

    assert asyncio.run(app_main.main()) == app_main.EXIT_BAD_TOKEN
    assert not polled, "до polling дело дойти не должно — токен уже отвергнут"
