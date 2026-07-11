# Telegram Music Bot

**Статус:** 🟢 прод (Этапы 1-3 + инфраструктура Этапа 4 задеплоены)
**Что это:** Telegram-бот [@tgram_music_bot](https://t.me/tgram_music_bot) — музыкальная платформа: библиотека, плейлисты, поиск, загрузка треков, Premium. Полное ТЗ — в [SPEC.md](SPEC.md).

## Прод

- VPS: `ssh news-rewriter-vps` (root@38.244.213.132), код в `/opt/tg-music-bot`
- Сервисы: `tg-music-bot` (polling) и `tg-music-worker` (Celery, обогащение загрузок). `systemctl {status,restart} tg-music-bot tg-music-worker`, логи: `journalctl -u <сервис> -f`
- Redis (`redis-server`) — FSM + брокер Celery. ffmpeg + libchromaprint-tools (fpcalc) — для отпечатков
- Repo: git@github.com:Mysterio3-8/telegram_music.git (пуш только по SSH — https-креды на машине от другого аккаунта)
- Деплой: `/deploy` (push → pull → pip install → `alembic upgrade head` → restart bot+worker)
- ⚠️ Не запускать бота локально, пока работает сервис на VPS — двойной polling конфликтует

## Архитектура

```
app/
├── main.py        # entrypoint: polling + FSM storage + middleware
├── config.py      # pydantic-settings, читает .env
├── fsm.py         # build_storage: Redis / in-memory
├── db/
│   ├── base.py    # engine, session_factory (схема — через Alembic)
│   └── models.py  # все 8 таблиц по SPEC §19
├── storage/       # хранилище аудио: LocalStorage / S3Storage, get_storage()
├── tasks/         # Celery: celery_app, enrich_track, enqueue_enrich
migrations/        # Alembic (env.py async, versions/)
├── services/      # бизнес-логика, НЕ знает о Telegram
│   ├── users.py     # get_or_create_user, счётчики, TelegramProfile
│   ├── library.py   # страницы, поиск, random, add/remove
│   ├── playlists.py # CRUD плейлистов, треки с позициями
│   ├── search.py    # поиск по общей базе (tracks + instrumentals)
│   ├── uploads.py   # валидация аудио, дубликаты по метаданным/отпечатку, создание трека
│   ├── fingerprint.py # chromaprint через fpcalc (graceful-фолбэк)
│   └── premium.py   # активация/продление, is_premium_active, лимиты (playlist/upload)
├── keyboards/     # inline-разметка, без логики (library, playlists, search, track_card, premium)
├── middlewares/
│   └── ads.py     # AdMiddleware: реклама каждое N-е действие бесплатных (SPEC §24)
└── handlers/      # роутинг апдейтов → вызов services
    ├── common.py        # ensure_user (+авто-снятие истёкшего Premium), format_duration
    ├── start.py         # /start (+deep-link track_{id}), кабинет, menu:main, noop
    ├── library.py       # экран библиотеки, FSM-поиск, random
    ├── playlists.py     # список/просмотр/создание/удаление плейлистов
    ├── search.py        # поиск треков и минусов, пагинация из FSM data
    ├── upload.py        # мастер загрузки (файл→название→исполнитель→подтверждение)
    ├── premium.py       # экран Premium, invoice/pre_checkout/successful_payment
    ├── cards.py         # карточка трека (без роутера, общая для разделов)
    ├── track_actions.py # trk:/ta:/back: — открытие карточки и действия с треком
    └── stubs.py         # Mini App (кнопка скрыта из меню)
tests/             # pytest + pytest-asyncio, in-memory sqlite
```

## Toolchain

- Python 3.10 (локально; на VPS 3.12), venv в `.venv/`
- aiogram 3.x, SQLAlchemy 2 async, pydantic-settings, Alembic, Celery, Redis, boto3
- БД: SQLite (dev, дефолт) / PostgreSQL через `DATABASE_URL` в `.env`; схема — Alembic
- FSM: Redis (`REDIS_URL`) с фолбэком на память. Хранилище: local / S3 (`S3_*`)
- Отпечатки: chromaprint `fpcalc` (система) + ffmpeg; нет бинарника → отпечаток пропускается

## Быстрые команды

```powershell
.\.venv\Scripts\python.exe -m pytest -q            # тесты
.\.venv\Scripts\python.exe -m alembic upgrade head # применить миграции (создаёт dev-БД)
.\.venv\Scripts\python.exe -m app.main             # запустить бота (нужен BOT_TOKEN в .env)
```

Новая миграция при изменении моделей (autogenerate против пустой временной БД):
```powershell
$env:DATABASE_URL="sqlite+aiosqlite:///_tmp.db"; .\.venv\Scripts\python.exe -m alembic upgrade head; .\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "..."; Remove-Item _tmp.db; Remove-Item Env:\DATABASE_URL
```

## Инварианты (нельзя нарушать)

- handlers/ не содержат бизнес-логику — только роутинг и форматирование текста
- services/ не импортируют aiogram — только SQLAlchemy и модели
- keyboards/ — только разметка
- Трек никогда не удаляется из `tracks` — только связи (user_library, playlist_tracks)
- Ровно 5 элементов на страницу (`settings.page_size`), навигация только Inline Keyboard
- callback_data соглашение: `menu:*` (меню), `lib:*` (библиотека), `pls:*`/`pl:*` (плейлисты), `st:`/`si:`/`ins:` (поиск), `up:*` (загрузка), `trk:`/`ta:`/`back:` (карточка трека; ctx = `lib.{page}` | `pl.{id}.{page}` | `srch`)
- Файлы треков: `tracks.tg_file_id` — для мгновенной пересылки; `tracks.storage_path` (`local://`/`s3://`) — архивная копия, ставит воркер обогащения. Ключ в хранилище — `tracks/{id}`
- Схема БД — только через Alembic-миграции, не create_all. Загрузка не должна ломаться, если Redis/Celery/fpcalc недоступны (graceful-фолбэк на границах)
- Один callback — один `callback.answer()`: shared-функции экранов (show_playlist_view и т.п.) не answer-ят, возвращают bool

## Что осталось (по этапам SPEC §30)

1. ~~Backend, БД, бот, авторизация, библиотека~~ ✅
2. ~~Поиск по общей базе, плейлисты, загрузка треков, дубликаты по метаданным~~ ✅ (Redis FSM и chromaprint-отпечатки отложены)
3. ~~Premium (Stars + карта/СБП), реклама~~ ✅ (карта/СБП ждёт `payment_provider_token`; логи оплаты — в journalctl)
4. Инфраструктура ✅ (Alembic, S3/local хранилище, Celery+Redis, chromaprint). **Осталось: модуль импорта каталога — блокирован источником (SPEC §23, нужны права)**
5. Mini App (кнопка скрыта в main_menu.py), FastAPI публичный API

## Известные грабли

- SQLite `ilike` нечувствителен к регистру только для ASCII — кириллический поиск станет регистронезависимым на PostgreSQL (`ILIKE`); на dev-SQLite это ожидаемое ограничение
- Схема БД — через Alembic. При адаптации существующей БД без `alembic_version`: `alembic stamp <ревизия-соответствующая-текущей-схеме>`, затем `upgrade head` (так приняли прод: stamp d01cfc648f91 → upgrade добавил tg_file_id)
- Обогащение (отпечаток+архив) — асинхронно в воркере: сразу после загрузки трека `storage_path` ещё пуст, появляется через секунды. Если воркер лежит — трек работает по `tg_file_id`, отпечаток не считается
- Windows-консоль: путь проекта с кириллицей, в PowerShell возможны артефакты кодировки в выводе — на работу не влияет

## Checkpoint (2026-07-11)

- Сделано: инфраструктура Этапа 4 задеплоена — Alembic вместо create_all (принят на прод-БД через stamp+upgrade, колонка tg_file_id добавлена без потери данных), слой хранилища (local dev / S3), сервис отпечатков chromaprint (проверен на проде — fpcalc 1.5.1), Celery-воркер `tg-music-worker` + Redis (FSM теперь durable), задача enrich_track (скачивание→отпечаток→архив) ставится при загрузке трека; 41 тест
- Активно: нет
- Следующий шаг: развилка. (а) Этап 4 «модуль импорта» — БЛОКИРОВАН: нужен легальный источник музыки от пользователя. (б) Этап 5 — Mini App + FastAPI публичный API (не блокирован)
- Не верифицировано вживую: полный цикл загрузки реального файла → обогащение (нельзя отправить файл боту от лица агента). Компоненты проверены по отдельности. При следующей загрузке смотреть `journalctl -u tg-music-worker -f` — должна появиться строка «Трек обогащён»
- Блокеры: карта/СБП ждёт `PAYMENT_PROVIDER_TOKEN`; модуль импорта ждёт источник
