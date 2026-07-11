# Telegram Music Bot

**Статус:** 🟢 прод (Этапы 1-2 из 5 задеплоены)
**Что это:** Telegram-бот [@tgram_music_bot](https://t.me/tgram_music_bot) — музыкальная платформа: библиотека, плейлисты, поиск, загрузка треков, Premium. Полное ТЗ — в [SPEC.md](SPEC.md).

## Прод

- VPS: `ssh news-rewriter-vps` (root@38.244.213.132), код в `/opt/tg-music-bot`
- Сервис: `systemctl {status,restart} tg-music-bot`, логи: `journalctl -u tg-music-bot -f`
- Repo: git@github.com:Mysterio3-8/telegram_music.git (пуш только по SSH — https-креды на машине от другого аккаунта)
- Деплой: `/deploy` (push → pull на сервере → restart)
- ⚠️ Не запускать бота локально, пока работает сервис на VPS — двойной polling конфликтует

## Архитектура

```
app/
├── main.py        # entrypoint: init_db + polling
├── config.py      # pydantic-settings, читает .env
├── db/
│   ├── base.py    # engine, session_factory, init_db (create_all)
│   └── models.py  # все 8 таблиц по SPEC §19
├── services/      # бизнес-логика, НЕ знает о Telegram
│   ├── users.py     # get_or_create_user, счётчики, TelegramProfile
│   ├── library.py   # страницы, поиск, random, add/remove
│   ├── playlists.py # CRUD плейлистов, треки с позициями
│   ├── search.py    # поиск по общей базе (tracks + instrumentals)
│   └── uploads.py   # валидация аудио, дубликаты по метаданным, создание трека
├── keyboards/     # inline-разметка, без логики (library, playlists, search, track_card)
└── handlers/      # роутинг апдейтов → вызов services
    ├── common.py        # ensure_user, format_duration
    ├── start.py         # /start (+deep-link track_{id}), кабинет, menu:main, noop
    ├── library.py       # экран библиотеки, FSM-поиск, random
    ├── playlists.py     # список/просмотр/создание/удаление плейлистов
    ├── search.py        # поиск треков и минусов, пагинация из FSM data
    ├── upload.py        # мастер загрузки (файл→название→исполнитель→подтверждение)
    ├── cards.py         # карточка трека (без роутера, общая для разделов)
    ├── track_actions.py # trk:/ta:/back: — открытие карточки и действия с треком
    └── stubs.py         # Premium (Этап 3), Mini App (скрыта из меню)
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
- callback_data соглашение: `menu:*` (меню), `lib:*` (библиотека), `pls:*`/`pl:*` (плейлисты), `st:`/`si:`/`ins:` (поиск), `up:*` (загрузка), `trk:`/`ta:`/`back:` (карточка трека; ctx = `lib.{page}` | `pl.{id}.{page}` | `srch`)
- Файлы треков — Telegram file_id в `storage_path` формата `tg://{file_id}` (S3 на Этапе 4)
- Один callback — один `callback.answer()`: shared-функции экранов (show_playlist_view и т.п.) не answer-ят, возвращают bool

## Что осталось (по этапам SPEC §30)

1. ~~Backend, БД, бот, авторизация, библиотека~~ ✅
2. ~~Поиск по общей базе, плейлисты, загрузка треков, дубликаты по метаданным~~ ✅ (Redis FSM и chromaprint-отпечатки отложены)
3. Premium (Stars + карта/СБП), реклама
4. Модуль импорта каталога, S3, Celery, Alembic-миграции вместо create_all, настоящий аудиоотпечаток
5. Mini App (кнопка скрыта в main_menu.py), FastAPI публичный API

## Известные грабли

- SQLite `ilike` нечувствителен к регистру только для ASCII — кириллический поиск станет регистронезависимым на PostgreSQL (`ILIKE`); на dev-SQLite это ожидаемое ограничение
- `create_all` не мигрирует существующие таблицы — при изменении моделей удалить `music_bot.db` или перейти на Alembic (Этап 4 → лучше раньше)
- Windows-консоль: путь проекта с кириллицей, в PowerShell возможны артефакты кодировки в выводе — на работу не влияет

## Checkpoint (2026-07-11)

- Сделано: Этап 2 целиком и задеплоен — поиск по общей базе (треки+минусы), плейлисты (CRUD, подтверждение удаления), мастер загрузки с валидацией и проверкой дубликатов по метаданным, общая карточка трека, скачивание по tg file_id, шеринг deep-link `/start track_{id}`; кнопка Mini App скрыта; 26 тестов
- Активно: нет
- Следующий шаг: Этап 3 — Premium (Telegram Stars, затем карта/СБП), счётчик действий и реклама для бесплатных
- Блокеры: нет. Замечание: BOT_TOKEN засветился в переписке — при желании сменить через /revoke у BotFather и обновить `.env` локально и на VPS
