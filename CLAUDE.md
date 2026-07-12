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
├── bot_commands.py # setup_bot_commands: /start (все) + /admin (персональный scope админов)
├── services/      # бизнес-логика, НЕ знает о Telegram
│   ├── users.py     # get_or_create_user, счётчики, TelegramProfile, is_admin
│   ├── library.py   # страницы, поиск, random, add/remove
│   ├── playlists.py # CRUD плейлистов, треки с позициями
│   ├── search.py    # поиск по общей базе (tracks + instrumentals, читает)
│   ├── instrumentals.py # запись минусов из админки: дедуп + создание (пишет)
│   ├── uploads.py   # валидация аудио, дубликаты по метаданным/отпечатку, создание трека
│   ├── subscription.py # обязательная подписка (§14-17): getChatMember + TTL-кэш
│   ├── fingerprint.py # chromaprint через fpcalc (graceful-фолбэк)
│   ├── track_meta.py # ID3-перетегирование (mutagen) + имя файла «Исполнитель — Название.ext»
│   ├── queue.py     # выборка пачек треков для очереди (микс/библиотека/плейлист/поиск)
│   ├── stats.py     # события listen/download + сводная статистика для админ-панели
│   ├── catalog_import.py # импорт в общую базу (треки/минусы/через API), дедуп
│   ├── youtube/     # metadata (парсер названия), downloader (yt-dlp), sources (очередь), importer
│   └── premium.py   # активация/продление, is_premium_active, лимиты (playlist/upload)
├── keyboards/     # inline-разметка, без логики (library, playlists, search, track_card, premium, player, admin, subscription)
├── middlewares/
│   ├── ads.py          # AdMiddleware: реклама каждое N-е действие бесплатных (SPEC §24)
│   └── subscription.py # SubscriptionMiddleware: гейт всех действий кроме /start и sub:check
└── handlers/      # роутинг апдейтов → вызов services
    ├── common.py        # ensure_user (+авто-снятие истёкшего Premium), format_duration
    ├── start.py         # /start (+deep-link track_{id}, гейт подписки), кабинет, menu:main, noop
    ├── subscription.py  # sub:check — принудительная перепроверка подписки
    ├── library.py       # экран библиотеки, FSM-поиск (микс — в player.py)
    ├── playlists.py     # список/просмотр/создание/удаление плейлистов
    ├── search.py        # поиск треков и минусов (ins:open:/ins:play:), пагинация из FSM data
    ├── upload.py        # мастер загрузки трека (файл→название→исполнитель→подтверждение)
    ├── admin_upload_minus.py # мастер загрузки минуса из админки — отдельный от upload.py, пишет в Instrumental
    ├── premium.py       # экран Premium, invoice/pre_checkout/successful_payment
    ├── cards.py         # карточка трека — аудиосообщение с плеером (без роутера, общая для разделов)
    ├── delivery.py      # выдача трека/минуса с кэшем file_id (send_track_audio/send_instrumental_audio, без роутера)
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
- callback_data соглашение: `menu:*` (меню), `lib:*` (библиотека), `pls:*`/`pl:*` (плейлисты), `st:`/`si:`/`ins:open:`/`ins:play:` (поиск), `up:*` (загрузка трека), `admin_min:*` (загрузка минуса из админки), `trk:`/`ta:`/`back:` (карточка трека; ctx = `lib.{page}` | `pl.{id}.{page}` | `srch`), `q:*` (очередь/микс), `adm:*` (админ-панель), `sub:check` (подтвердить подписку)
- Карточка трека — отдельное аудиосообщение (не заменяет экран списка); `back:del` удаляет её, `back:{ctx}` — легаси-навигация для старых сообщений
- Файлы треков: `tracks.tg_file_id` — для мгновенной пересылки; `tracks.storage_path` (`local://`/`s3://`) — архивная копия, ставит воркер обогащения. Ключ в хранилище — `tracks/{id}`. Минусы — та же схема в `instrumentals` (`instrumentals.tg_file_id`/`storage_path`, ключ `instrumentals/{id}`), но отдельная таблица от `tracks` — совпадение title/artist с треком не дубликат (TZ §9)
- Выдача аудио — только через `handlers/delivery.send_track_audio` (треки) / `send_instrumental_audio` (минусы): гарантируют мгновенную пересылку по кэшированному file_id; `send_track_audio` дополнительно держит актуальные ID3-теги и имя файла «Исполнитель — Название.ext» (`meta_synced=False` → перетегировать и переотправить) и пишет события статистики
- Схема БД — только через Alembic-миграции, не create_all. Загрузка не должна ломаться, если Redis/Celery/fpcalc недоступны (graceful-фолбэк на границах)
- Один callback — один `callback.answer()`: shared-функции экранов (show_playlist_view и т.п.) не answer-ят, возвращают bool
- Обязательная подписка (§14-17): `SubscriptionMiddleware` гейтит все message/callback хендлеры кроме `/start` и `sub:check` (у них своя принудительная проверка). Кэш в `subscription_status` с TTL `SUBSCRIPTION_CACHE_TTL_MINUTES`; при ошибке Telegram API — fail-closed (считаем неподписанным). `ADMIN_BYPASS_SUBSCRIPTION=true` освобождает админов

## Что осталось (по этапам SPEC §30)

1. ~~Backend, БД, бот, авторизация, библиотека~~ ✅
2. ~~Поиск по общей базе, плейлисты, загрузка треков, дубликаты по метаданным~~ ✅ (Redis FSM и chromaprint-отпечатки отложены)
3. ~~Premium (Stars + карта/СБП), реклама~~ ✅ (карта/СБП ждёт `payment_provider_token`; логи оплаты — в journalctl)
4. ~~Инфраструктура + модуль импорта~~ ✅ (Alembic, S3/local хранилище, Celery+Redis, chromaprint; импортёр: `python -m app.cli.import_catalog <dir> [--instrumental] [--artist X]`, дедуп по отпечатку+метаданным). Коннекторы к внешним источникам — по мере появления прав
5. FastAPI публичный API ✅ (app/api, JWT + Telegram WebApp initData; как сервис НЕ развёрнут — ждёт Mini App и домена/HTTPS). Mini App — ждёт чертежи пользователя (кнопка скрыта в main_menu.py)
6. Апдейт по доп. ТЗ (обязательная подписка, минусы, быстрые команды) — независимые срезы ✅: подписка на 2 канала (§14-17), воспроизведение+загрузка минусов через админку (§9-11), /start-/admin scope команд (§12-13). Player Engine и настоящий автоплей через Mini App (§3-8) — отложены осознанно (нужен домен/HTTPS), архитектура (Instrumental, delivery-слой) готова принять Mini App позже без переделки

## Известные грабли

- SQLite `ilike` нечувствителен к регистру только для ASCII — кириллический поиск станет регистронезависимым на PostgreSQL (`ILIKE`); на dev-SQLite это ожидаемое ограничение
- Схема БД — через Alembic. При адаптации существующей БД без `alembic_version`: `alembic stamp <ревизия-соответствующая-текущей-схеме>`, затем `upgrade head` (так приняли прод: stamp d01cfc648f91 → upgrade добавил tg_file_id)
- Обогащение (отпечаток+архив) — асинхронно в воркере: сразу после загрузки трека `storage_path` ещё пуст, появляется через секунды. Если воркер лежит — трек работает по `tg_file_id`, отпечаток не считается
- Windows-консоль: путь проекта с кириллицей, в PowerShell возможны артефакты кодировки в выводе — на работу не влияет

## Checkpoint (2026-07-12)

- Сделано: реализованы 3 независимых среза доп. ТЗ (129 тестов, было 120):
  1. Обязательная подписка (§14-17): модель `SubscriptionStatus`, `services/subscription.py` (getChatMember + TTL-кэш, fail-closed), `SubscriptionMiddleware` на все хендлеры кроме `/start`/`sub:check`, гейт-экран с кнопками на 2 канала + «Проверить подписку», `ADMIN_BYPASS_SUBSCRIPTION`. Миграция `a1c2e3f4b5d6`
  2. Минусы доиграны до рабочего состояния (`Instrumental` уже существовал, но не имел воспроизведения и загрузки из бота): добавлены `tg_file_id`/`source`/`created_at`, `send_instrumental_audio`, кнопка «▶️ Слушать» в карточке минуса, мастер загрузки минусов из админки (`admin_upload_minus.py`, дедуп только внутри `instrumentals`, не пересекается с `tracks`). Миграция `b2d3e4f5a6c7`
  3. Быстрые команды (§12-13): `app/bot_commands.py` — `/start` в дефолтном scope, `/admin` только в персональном scope админов (`BotCommandScopeChat`); backend-проверка `is_admin` уже была на месте
  - Заодно: `is_admin` перенесён из `handlers/cards.py` в `services/users.py` (нужен был `services/subscription.py`, а services не должны зависеть от handlers)
- Активно: нет
- Следующий шаг: задеплоить (`/deploy`), вписать реальный `ADMIN_IDS` в `.env` на VPS (пользователь подтвердил, что ID известен, но фактическое значение не передано — нужно получить у пользователя, напр. через @userinfobot, SSH-чтение .env заблокировано классификатором); бот уже подтверждён администратором в @tgramuzuka и @zvyagaminus — подписку можно тестировать сразу после деплоя
- Осознанно отложено: Player Engine + настоящий автоплей через Mini App (§3-8 доп. ТЗ) — требует публичного HTTPS-домена для VPS 38.244.213.132, которого пока нет; пользователь подтвердил делать это отдельным этапом, когда появятся чертежи
- Блокеры: карта/СБП ждёт `PAYMENT_PROVIDER_TOKEN`; Mini App ждёт домен/HTTPS + чертежи; API-сервис не поднят
