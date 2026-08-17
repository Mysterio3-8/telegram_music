"""Отсев мёртвых file_id перед инлайн-выдачей.

Инлайн — единственное место, где самолечение «поймали ошибку при отправке»
невозможно: файл отправляет Telegram, а не мы, и об отказе нам не сообщают.
Поэтому проверка идёт до выдачи, и у неё есть два ограничения, которые легко
снести не подумав, — на них здесь отдельные тесты.
"""
import pytest
from aiogram.exceptions import TelegramBadRequest

from app.db.models import Instrumental, Track, User
from app.services import file_id_health
from app.services.file_id_health import (
    bury_dead_tracks,
    is_alive,
    split_by_liveness,
)


class FakeBot:
    """Telegram, который считает мёртвым всё, кроме перечисленного."""

    def __init__(self, alive: set[str]):
        self.alive = alive
        self.calls: list[str] = []

    async def get_file(self, file_id: str):
        self.calls.append(file_id)
        if file_id in self.alive:
            return object()
        raise TelegramBadRequest(method=None, message="wrong file identifier")


@pytest.fixture(autouse=True)
def _clear_cache():
    file_id_health._verdicts.clear()
    yield
    file_id_health._verdicts.clear()


def _t(id_, file_id):
    return Track(id=id_, artist="Артист", title=f"Трек {id_}", duration=180, tg_file_id=file_id)


@pytest.mark.asyncio
async def test_dead_ids_do_not_reach_the_answer():
    bot = FakeBot(alive={"good"})
    alive, dead = await split_by_liveness(bot, [_t(1, "dead"), _t(2, "good")])

    assert [t.id for t in alive] == [2]
    assert [t.id for t in dead] == [1]


@pytest.mark.asyncio
async def test_budget_caps_calls_to_telegram():
    """Инлайн-запрос прилетает на каждое нажатие клавиши: без потолка это
    десятки обращений к Bot API в секунду, то есть свой собственный флуд."""
    bot = FakeBot(alive={f"id{i}" for i in range(50)})
    tracks = [_t(i, f"id{i}") for i in range(50)]

    alive, _ = await split_by_liveness(bot, tracks, budget=5)

    assert len(bot.calls) == 5
    assert len(alive) == 5


@pytest.mark.asyncio
async def test_verdicts_are_cached_between_queries():
    """Наборы результатов при наборе текста сильно пересекаются — второй запрос
    не должен снова спрашивать Telegram о тех же файлах."""
    bot = FakeBot(alive={"good"})
    await split_by_liveness(bot, [_t(1, "good")])
    await split_by_liveness(bot, [_t(1, "good")])

    assert len(bot.calls) == 1


@pytest.mark.asyncio
async def test_network_hiccup_does_not_kill_a_track():
    """Сбой сети — не приговор: трек считается живым и будет проверен позже."""

    class BrokenBot:
        async def get_file(self, file_id: str):
            raise TimeoutError("сеть моргнула")

    assert await is_alive(BrokenBot(), "whatever") is True
    # и вердикт не запомнен — иначе час бы считали живым по ошибке сети
    assert "whatever" not in file_id_health._verdicts


@pytest.mark.asyncio
async def test_burying_marks_all_but_queues_one(session, monkeypatch):
    """🔴 Пул из тридцати треков сейчас — это почти тридцать мёртвых. Поставить
    их все на восстановление значило бы положить на единственное ядро четыре
    минуты работы за одно нажатие клавиши (так уже было: очередь на 177 тысяч
    задач и OOM, инцидент 03.08). Гасим все, чиним один."""
    queued = []

    class FakeTask:
        def delay(self, **kwargs):
            queued.append(kwargs)

    import app.tasks.search_fetch as search_fetch

    monkeypatch.setattr(search_fetch, "repair_track", FakeTask(), raising=False)

    dead = [_t(i, f"dead{i}") for i in range(1, 6)]
    session.add_all(dead)
    await session.commit()

    await bury_dead_tracks(session, dead)

    assert all(t.tg_file_id is None for t in dead)
    assert all(t.meta_synced is False for t in dead)
    assert len(queued) == 1
    # молча: инлайн-запрос — не просьба прислать файл в чат
    assert queued[0]["chat_id"] is None


@pytest.mark.asyncio
async def test_instrumentals_are_filtered_but_never_buried():
    """⚠️ У минусов нет источника для перезакачки — они пришли из ТГ-канала.
    Погасить им file_id значило бы потерять единственную ссылку на файл
    безвозвратно, поэтому мёртвые просто не показываются."""
    bot = FakeBot(alive=set())
    minus = Instrumental(id=1, artist="A", title="B", tg_file_id="dead")

    alive, dead = await split_by_liveness(bot, [minus])

    assert alive == []
    assert dead == [minus]
    # bury_dead_tracks к ним не применяется — id остаётся на месте
    assert minus.tg_file_id == "dead"


# --- выдача трека: мёртвый id лечится в ОБЕИХ ветках --------------------------------


@pytest.mark.asyncio
async def test_delivery_repairs_dead_id_without_archive(session, monkeypatch):
    """🔴 Ветка «байты недоступны» отправляла файл БЕЗ перехвата ошибки. Трек с
    meta_synced=False (метаданные правил админ) и мёртвым id ронял обработчик:
    человек получал общую ошибку, а восстановление никто не ставил — то есть
    при следующем обращении повторялось то же самое."""
    from app.handlers import delivery

    track = Track(
        id=1, artist="Артист", title="Трек", duration=180,
        tg_file_id="dead", meta_synced=False, storage_path=None,
    )
    user = User(telegram_id=777)
    session.add_all([track, user])
    await session.commit()

    scheduled = []

    async def fake_repair(sess, trk, chat_id):
        scheduled.append(trk.id)

    monkeypatch.setattr(delivery, "_schedule_repair", fake_repair)

    class DeadBot:
        async def send_audio(self, *a, **kw):
            raise TelegramBadRequest(method=None, message="wrong file identifier")

        async def download(self, *a, **kw):
            raise TelegramBadRequest(method=None, message="wrong file identifier")

    result = await delivery.send_track_audio(
        DeadBot(), chat_id=1, session=session, user=user, track=track
    )

    assert result is None
    assert scheduled == [1]
