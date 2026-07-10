# Telegram Music Bot

**Статус:** 🟡 dev (Этап 1 из 5)
**Что это:** Telegram-бот — музыкальная платформа: библиотека, плейлисты, поиск, загрузка треков, Premium. Полное ТЗ — в [SPEC.md](SPEC.md).

## Архитектура

```
app/
├── main.py        # entrypoint: init_db + polling
├── config.py      # pydantic-settings, читает .env
├── db/
│   ├── base.py    # engine, session_factory, init_db (create_all)
│   └── models.py  # все 8 таблиц по SPEC §19
├── services/      # бизнес-логика, НЕ знает о Telegram
│   ├── users.py   # get_or_create_user, счётчики, TelegramProfile
│   └── library.py # страницы, поиск, random, add/remove
├── keyboards/     # inline-разметка, без логики
└── handlers/      # роутинг апдейтов → вызов services
    ├── common.py  # ensure_user (aiogram User → TelegramProfile), format_duration
    ├── start.py   # /start, личный кабинет, menu:main, noop
    ├── library.py # экран библиотеки, FSM-поиск, карточка трека
    └── stubs.py   # разделы этапов 2-3 (alert-заглушки)
tests/             # pytest + pytest-asyncio, in-memory sqlite
```

## Toolchain

- Python 3.10 (локально; ТЗ целится в 3.13 на проде), venv в `.venv/`
- aiogram 3.x, SQLAlchemy 2 async, pydantic-settings
- БД: SQLite (dev, дефолт) / PostgreSQL через `DATABASE_URL` в `.env`
- FSM-хранилище: memory (Redis подключим на Этапе 2)

## Быстрые команды

```powershell
.\.venv\Scripts\python.exe -m pytest -q        # тесты
.\.venv\Scripts\python.exe -m app.main         # запустить бота (нужен BOT_TOKEN в .env)
```

## Инварианты (нельзя нарушать)

- handlers/ не содержат бизнес-логику — только роутинг и форматирование текста
- services/ не импортируют aiogram — только SQLAlchemy и модели
- keyboards/ — только разметка
- Трек никогда не удаляется из `tracks` — только связи (user_library, playlist_tracks)
- Ровно 5 элементов на страницу (`settings.page_size`), навигация только Inline Keyboard
- callback_data соглашение: `menu:*` (главное меню), `lib:*` (библиотека), `stub:*` (заглушки)

## Что осталось (по этапам SPEC §30)

1. ~~Backend, БД, бот, авторизация, библиотека~~ ✅
2. Поиск по общей базе, плейлисты, загрузка треков, дубликаты (fingerprint), Redis FSM
3. Premium (Stars + карта/СБП), реклама
4. Модуль импорта каталога, S3, Celery, Alembic-миграции вместо create_all
5. Mini App, FastAPI публичный API

## Известные грабли

- SQLite `ilike` нечувствителен к регистру только для ASCII — кириллический поиск станет регистронезависимым на PostgreSQL (`ILIKE`); на dev-SQLite это ожидаемое ограничение
- `create_all` не мигрирует существующие таблицы — при изменении моделей удалить `music_bot.db` или перейти на Alembic (Этап 4 → лучше раньше)
- Windows-консоль: путь проекта с кириллицей, в PowerShell возможны артефакты кодировки в выводе — на работу не влияет

## Checkpoint (2026-07-10)

- Сделано: Этап 1 целиком — SPEC.md, скелет проекта, 8 моделей БД, /start-кабинет, библиотека (пагинация 5/стр, поиск по библиотеке через FSM, случайный трек, карточка трека, удаление из библиотеки), заглушки разделов, 10 юнит-тестов зелёные
- Активно: нет
- Следующий шаг: Этап 2 — плейлисты (CRUD + экраны по SPEC §7-8), затем загрузка треков
- Блокеры: для живого запуска нужен BOT_TOKEN от @BotFather в `.env`
