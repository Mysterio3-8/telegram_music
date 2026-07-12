from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommandScopeChat, BotCommandScopeDefault

from app.bot_commands import setup_bot_commands
from app.config import settings


class FakeBot:
    def __init__(self, fail_for: set[int] | None = None):
        self.calls = []
        self.fail_for = fail_for or set()

    async def set_my_commands(self, commands, scope):
        if isinstance(scope, BotCommandScopeChat) and scope.chat_id in self.fail_for:
            raise TelegramAPIError(method=None, message="chat not found")
        self.calls.append((commands, scope))


async def test_setup_bot_commands_sets_default_and_admin_scopes(monkeypatch):
    monkeypatch.setattr(settings, "admin_ids", "111,222")
    bot = FakeBot()

    await setup_bot_commands(bot)

    default_calls = [c for c in bot.calls if isinstance(c[1], BotCommandScopeDefault)]
    admin_calls = [c for c in bot.calls if isinstance(c[1], BotCommandScopeChat)]
    assert len(default_calls) == 1
    assert {"start"} == {cmd.command for cmd in default_calls[0][0]}
    assert {c[1].chat_id for c in admin_calls} == {111, 222}
    for commands, _scope in admin_calls:
        assert {"start", "admin"} == {cmd.command for cmd in commands}


async def test_setup_bot_commands_tolerates_admin_scope_failure(monkeypatch):
    monkeypatch.setattr(settings, "admin_ids", "111,222")
    bot = FakeBot(fail_for={111})

    await setup_bot_commands(bot)  # не должно бросать исключение

    admin_calls = [c for c in bot.calls if isinstance(c[1], BotCommandScopeChat)]
    assert {c[1].chat_id for c in admin_calls} == {222}
