# Telegram Music Bot

**Статус:** 🟢 прод (Этапы 1-3 + инфраструктура Этапа 4 задеплоены)
**Что это:** Telegram-бот [@tgram_music_bot](https://t.me/tgram_music_bot) — музыкальная платформа: библиотека, плейлисты, поиск, загрузка треков, Premium. Полное ТЗ — в [SPEC.md](SPEC.md).

## Прод

- VPS: `ssh news-rewriter-vps` (root@38.244.213.132), код в `/opt/tg-music-bot`
- Сервисы: `tg-music-bot` (polling), `tg-music-worker` (Celery, обогащение загрузок), `tg-music-youtube` (Celery, очередь `youtube` — импорт с YouTube), таймер `tg-music-youtube-scan` (автопроверка §11). Юниты — в [deploy/](deploy/). `systemctl {status,restart} <сервис>`, логи: `journalctl -u <сервис> -f`
- Redis (`redis-server`) — FSM + брокер Celery. ffmpeg + libchromaprint-tools (fpcalc) — отпечатки. yt-dlp (pip) — загрузка с YouTube
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
├── tasks/         # Celery: celery_app, enrich_track, youtube (scan/process/recover/scan_due)
├── importers/     # ImportSource: LocalDirectorySource (mutagen)
├── api/           # FastAPI публичный REST (§27): login(initData→JWT), tracks, library, upload…
├── cli/           # import_catalog (папка), youtube (управление источниками)
migrations/        # Alembic (env.py async, versions/)
├── services/      # бизнес-логика, НЕ знает о Telegram
│   ├── users.py     # get_or_create_user, счётчики, TelegramProfile
│   ├── library.py   # страницы, поиск, random, add/remove
│   ├── playlists.py # CRUD плейлистов, треки с позициями
│   ├── search.py    # поиск по общей базе (tracks + instrumentals)
│   ├── uploads.py   # валидация аудио, дубликаты по метаданным/отпечатку, создание трека
│   ├── fingerprint.py # chromaprint через fpcalc (graceful-фолбэк)
│   ├── track_meta.py # ID3-перетегирование (mutagen) + имя файла «Исполнитель — Название.ext»
│   ├── queue.py     # выборка пачек треков для очереди (микс/библиотека/плейлист/поиск)
│   ├── stats.py     # события listen/download + сводная статистика для админ-панели
│   ├── catalog_import.py # импорт в общую базу (треки/минусы/через API), дедуп
│   ├── youtube/     # metadata (парсер названия), downloader (yt-dlp), sources (очередь), importer
│   └── premium.py   # активация/продление, is_premium_active, лимиты (playlist/upload)
├── keyboards/     # inline-разметка, без логики (library, playlists, search, track_card, premium, player, admin)
├── middlewares/
│   └── ads.py     # AdMiddleware: реклама каждое N-е действие бесплатных (SPEC §24)
└── handlers/      # роутинг апдейтов → вызов services
    ├── common.py        # ensure_user (+авто-снятие истёкшего Premium), format_duration
    ├── start.py         # /start (+deep-link track_{id}), кабинет, menu:main, noop
    ├── library.py       # экран библиотеки, FSM-поиск (микс — в player.py)
    ├── playlists.py     # список/просмотр/создание/удаление плейлистов
    ├── search.py        # поиск треков и минусов, пагинация из FSM data
    ├── upload.py        # мастер загрузки (файл→название→исполнитель→подтверждение)
    ├── premium.py       # экран Premium, invoice/pre_checkout/successful_payment
    ├── cards.py         # карточка трека — аудиосообщение с плеером (без роутера, общая для разделов)
    ├── delivery.py      # выдача аудио с актуальными тегами/именем + кэш file_id (без роутера)
    ├── player.py        # q:* — очередь воспроизведения и режим «Микс»
    ├── admin.py         # /admin (статистика), ta:edit — правка метаданных трека
    ├── admin_youtube.py # adm:yt* — управление YouTube-источниками (§17)
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
- callback_data соглашение: `menu:*` (меню), `lib:*` (библиотека), `pls:*`/`pl:*` (плейлисты), `st:`/`si:`/`ins:` (поиск), `up:*` (загрузка), `trk:`/`ta:`/`back:` (карточка трека; ctx = `lib.{page}` | `pl.{id}.{page}` | `srch`), `q:*` (очередь/микс), `adm:*` (админ-панель)
- Карточка трека — отдельное аудиосообщение (не заменяет экран списка); `back:del` удаляет её, `back:{ctx}` — легаси-навигация для старых сообщений
- Файлы треков: `tracks.tg_file_id` — для мгновенной пересылки; `tracks.storage_path` (`local://`/`s3://`) — архивная копия, ставит воркер обогащения. Ключ в хранилище — `tracks/{id}`
- Выдача аудио — только через `handlers/delivery.send_track_audio`: она гарантирует актуальные ID3-теги и имя файла «Исполнитель — Название.ext» (`meta_synced=False` → перетегировать и переотправить, кэшировать новый file_id) и пишет события статистики
- Схема БД — только через Alembic-миграции, не create_all. Загрузка не должна ломаться, если Redis/Celery/fpcalc недоступны (graceful-фолбэк на границах)
- Один callback — один `callback.answer()`: shared-функции экранов (show_playlist_view и т.п.) не answer-ят, возвращают bool

## Что осталось (по этапам SPEC §30)

1. ~~Backend, БД, бот, авторизация, библиотека~~ ✅
2. ~~Поиск по общей базе, плейлисты, загрузка треков, дубликаты по метаданным~~ ✅ (Redis FSM и chromaprint-отпечатки отложены)
3. ~~Premium (Stars + карта/СБП), реклама~~ ✅ (карта/СБП ждёт `payment_provider_token`; логи оплаты — в journalctl)
4. ~~Инфраструктура + модуль импорта~~ ✅ (Alembic, S3/local хранилище, Celery+Redis, chromaprint; импортёр: `python -m app.cli.import_catalog <dir> [--instrumental] [--artist X]`, дедуп по отпечатку+метаданным). Коннекторы к внешним источникам — по мере появления прав
5. FastAPI публичный API ✅ (app/api, JWT + Telegram WebApp initData; как сервис НЕ развёрнут — ждёт Mini App и домена/HTTPS). Mini App — ждёт чертежи пользователя (кнопка скрыта в main_menu.py)

## Известные грабли

- SQLite `ilike` нечувствителен к регистру только для ASCII — кириллический поиск станет регистронезависимым на PostgreSQL (`ILIKE`); на dev-SQLite это ожидаемое ограничение
- Схема БД — через Alembic. При адаптации существующей БД без `alembic_version`: `alembic stamp <ревизия-соответствующая-текущей-схеме>`, затем `upgrade head` (так приняли прод: stamp d01cfc648f91 → upgrade добавил tg_file_id)
- Обогащение (отпечаток+архив) — асинхронно в воркере: сразу после загрузки трека `storage_path` ещё пуст, появляется через секунды. Если воркер лежит — трек работает по `tg_file_id`, отпечаток не считается
- Windows-консоль: путь проекта с кириллицей, в PowerShell возможны артефакты кодировки в выводе — на работу не влияет

## Checkpoint (2026-07-11, ночь)

- Сделано: (а) пакет доработок из PR #1 задеплоен на VPS (миграция b3e91a7c42d0 применена: track_events + meta_synced); (б) домержены модуль импорта каталога + FastAPI API (§27), конфликт .env.example разрешён, 72 теста; (в) первый массовый импорт на прод: 42 минуса (биты DJ Kale из ПРОДАЖА/ТРЕКИ\биты) + 13 треков (альбом First/Pearly Pride, синглы) — у всех chromaprint-отпечатки и файлы в local-хранилище (182 МБ), дедуп поймал 1 дубликат
- Активно: нет
- Следующий шаг: ADMIN_IDS в .env на VPS (ждёт подтверждения ID пользователем — авто-запись заблокировал классификатор); проверить вживую выдачу импортированного трека (у них нет tg_file_id — delivery отправит из хранилища и закэширует); Mini App — ждёт чертежи
- НЕ импортировано (нет прав на раздачу): треки Big Baby Tape/kizaru/BONES/Three 6 Mafia и др. коммерческие из ремикс-папок Desktop. В импорт попал «Кино — Группа крови» (тег в файле из ПРОДАЖА) — проверить/удалить через админку
- Ограничение Bot API (осознанное): событий «трек дослушан» нет — микс/очередь пачками по `QUEUE_BATCH_SIZE` с кнопкой «Продолжить»; getFile ≤ 20 МБ
- Блокеры: карта/СБП ждёт `PAYMENT_PROVIDER_TOKEN`; Mini App ждёт чертежи; API-сервис не поднят (нужен домен/HTTPS под Mini App)
