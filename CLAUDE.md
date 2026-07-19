# Telegram Music Bot

**Статус:** 🟢 прод (Этапы 1-5 задеплоены, Mini App живой на keybest.cc)
**Что это:** Telegram-бот [@tgram_music_bot](https://t.me/tgram_music_bot) — музыкальная платформа: библиотека, плейлисты, поиск, загрузка треков, Premium. Полное ТЗ — в [SPEC.md](SPEC.md).

## Прод

- VPS: `ssh news-rewriter-vps` (root@38.244.213.132), код в `/opt/tg-music-bot`
- Домен: **keybest.cc — жив, HTTPS выпущен** (Let's Encrypt, автопродление certbot, истекает 2026-10-10). nginx-сайт `/etc/nginx/sites-enabled/keybest.cc` (источник — [deploy/nginx-keybest.conf](deploy/nginx-keybest.conf)): статика Mini App на `/`, `/api/` → uvicorn :8010, `/webhook/` → uvicorn :8010
- Сервисы: `tg-music-bot` (polling), `tg-music-worker` (Celery, обогащение загрузок), `tg-music-youtube` (Celery, очередь `youtube` — импорт с YouTube), таймер `tg-music-youtube-scan` (автопроверка §11), `tg-music-api` (uvicorn :8010 — API Mini App + webhook ЮKassa). Юниты — в [deploy/](deploy/), nginx-сайт — [deploy/nginx-keybest.conf](deploy/nginx-keybest.conf). `systemctl {status,restart} <сервис>`, логи: `journalctl -u <сервис> -f`
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

## Правило релизов

**После каждого деплоя — добавить пост в [NEWS.md](NEWS.md)** (новые сверху) о том, что добавили: заголовок + суть одним предложением + 2-4 пункта ▪️ + короткий путь по кнопкам. Стиль — средний: не сухой список, но без воды. Владелец публикует посты в свой новостной канал сам. Шаблон — внизу NEWS.md.

## Инварианты (нельзя нарушать)

- handlers/ не содержат бизнес-логику — только роутинг и форматирование текста
- services/ не импортируют aiogram — только SQLAlchemy и модели (исключение: импортёры, минтящие file_id через бота)
- keyboards/ — только разметка
- Трек никогда не удаляется из `tracks` — только связи (user_library, playlist_tracks). **Единственное исключение** (решение владельца): админ-очистка не-музыки `adm:junk:*` — треки вне границ `track_min_seconds..track_max_seconds` удаляются полностью (файл + связи + запись), с подтверждением. **Лимиты по длительности сняты владельцем** (`track_min_seconds=track_max_seconds=0` → фильтр выключен, junk-очистка ничего не находит; `0` = «без лимита» и для `free_upload_limit`, `playlist_import_limit`)
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
5. FastAPI публичный API ✅ развёрнут (`tg-music-api.service`, uvicorn :8010, за nginx на keybest.cc)
6. Апдейт по доп. ТЗ (обязательная подписка, минусы, быстрые команды) — независимые срезы ✅: подписка на 2 канала (§14-17), воспроизведение+загрузка минусов через админку (§9-11), /start-/admin scope команд (§12-13)
7. Mini App-плеер (§3-8) ✅ задеплоен на keybest.cc: настоящий автоплей через `<audio>` + `ended` (никаких пачек по QUEUE_BATCH_SIZE для Mini App), очередь-шаффл без повторов, обе темы (Premium Black Amethyst), оплата Premium через ЮKassa (21 ₽, redirect + webhook). Бот-меню: кнопка «🎧 Открыть плеер» первая в списке (WebAppInfo, показывается по `PUBLIC_BASE_URL`)

## Известные грабли

- **keybest.cc в Google Safe Browsing** (Safari/Chrome показывают «Deceptive Website Warning»). Снятие: [Google Search Console](https://search.google.com/search-console) → добавить ресурс **Домен** `keybest.cc` → подтвердить TXT-записью в DNS → раздел **Безопасность и меры** (Security & Manual Actions) → посмотреть причину → **Запросить проверку**. Ответ 1-3 дня. Проверить статус: `https://transparencyreport.google.com/safe-browsing/search?url=keybest.cc`. Зона `.cc` часто в группе риска — если флаг вернётся, переезжать на `.ru`/`.com`

- SQLite `ilike` нечувствителен к регистру только для ASCII — кириллический поиск станет регистронезависимым на PostgreSQL (`ILIKE`); на dev-SQLite это ожидаемое ограничение
- Схема БД — через Alembic. При адаптации существующей БД без `alembic_version`: `alembic stamp <ревизия-соответствующая-текущей-схеме>`, затем `upgrade head` (так приняли прод: stamp d01cfc648f91 → upgrade добавил tg_file_id)
- Обогащение (отпечаток+архив) — асинхронно в воркере: сразу после загрузки трека `storage_path` ещё пуст, появляется через секунды. Если воркер лежит — трек работает по `tg_file_id`, отпечаток не считается
- Windows-консоль: путь проекта с кириллицей, в PowerShell возможны артефакты кодировки в выводе — на работу не влияет

## Checkpoint (2026-07-18, SoundCloud с любой страницы + разделение очередей)

- **Скачивание с любой страницы SoundCloud** (запрос владельца «хоть весь soundcloud»): `normalize_soundcloud_url` ([soundcloud.py](app/services/soundcloud.py)) теперь сворачивает к профилю только реально сломанный `/popular-tracks`/`top-tracks`; `/tracks`, `/likes`, `/reposts`, `/sets`, `/albums` yt-dlp открывает напрямую — качаем именно их. Страница поиска `/search?q=` и тега `/tags/` → `scsearch<N>:запрос` (`soundcloud_search_limit`, дефолт 200). normalize идемпотентен. Проверено на проде: лайки→1990, поиск→200, тег→200
- **Разделены очереди Celery** (было: «треки не качаются» — новые источники стояли в хвосте бэклога): `soundcloud.*` → очередь `soundcloud` (юнит [tg-music-soundcloud.service](deploy/tg-music-soundcloud.service)), `youtube.user_import` (ссылки от юзеров бота) → очередь `youtube_user` (юнит [tg-music-youtube-user.service](deploy/tg-music-youtube-user.service), concurrency=2), массовые сканы каналов остались в `youtube`. Задачи SoundCloud вынесены в [app/tasks/soundcloud.py](app/tasks/soundcloud.py). ⚠️ Новые юниты: `cp deploy/*.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now tg-music-soundcloud tg-music-youtube-user`
- **impersonation теперь opt-in**: `_base_opts(impersonate=True)` только для SoundCloud (YouTube на чужой TLS-отпечаток отвечал 403). DRM/приватные треки SoundCloud метятся обработанными сразу — не ретраятся вечно
- Тесты: **195 passed**

## Checkpoint (2026-07-18, анти-бан SoundCloud) — 3 причины «0 треков» устранены

Владелец добавил SoundCloud-источник `.../popular-tracks` → «Найдено 0». Три бага, все исправлены:
1. **`/popular-tracks` и др. вкладки профиля → 404** у yt-dlp. `normalize_soundcloud_url` ([soundcloud.py](app/services/soundcloud.py)) сворачивает вкладки (`/popular-tracks`, `/tracks`, `/likes`, `/sets`, …) к корню профиля; трек и `/sets/<name>` не трогает. Нормализация и при добавлении, и при скане — чинит уже сохранённые источники
2. **celery `--pool=prefork` ломал нативную сеть yt-dlp после fork()** → воркер стабильно отдавал 0, хотя CLI в свежем процессе — сотни треков. Юнит [tg-music-youtube.service](deploy/tg-music-youtube.service) переведён на `--pool=threads --concurrency=1` (без fork, без параллельных всплесков). ⚠️ При деплое юнита — `cp deploy/*.service /etc/systemd/system/ && systemctl daemon-reload`
3. **curl_cffi impersonation** ([downloader.py](app/services/youtube/downloader.py) `_base_opts`) — SoundCloud отдаёт 404 на частых запросах без Chrome-impersonation. Добавлен в requirements
- **Анти-бан (запрос владельца «чтобы не банили IP»)**: таблица `soundcloud_imported` (миграция `d1e2f3a4b5c7`) — обработанные ссылки не качаются повторно, rescan бьёт по сети только по новым. Троттлинг: пауза 2-5с между скачиваниями + `sleep_interval_requests=1`. Отчёт скана показывает «пропущено ранее обработанных»
- На проде: источник #1 (`/search?q=kizaru` — не профиль) отключён. Активны tapeboss/kizaru_hf/aarne0 — импортируются инкрементально по ежедневному таймеру
- Тесты: **193 passed** (+7: нормализация, инкрементальный пропуск)

## Checkpoint (2026-07-18, уточнение владельца) — SoundCloud/YT Music = ТРЕКИ, минусы только из ТГ-канала

- **SoundCloud → треки** (не минусы): [soundcloud_import.py](app/services/soundcloud_import.py) → `import_soundcloud_tracks` через `import_via_telegram_mint` (общая база). Приём ссылки перенесён из мастера «Загрузить минус» (там снова только файл) в админ-раздел «🎬 Источники треков» (`adm:yt:add` принимает YouTube/YT Music/SoundCloud; SoundCloud-источники видны списком в тексте раздела, управление — пока CLI/БД)
- Минусы — только ТГ-канал (`--instrumental` у telegram_channel add); `import_instrumental_via_telegram_mint` остаётся для этой ветки
- Автопроверка без изменений: SoundCloud ежедневно, YouTube на проде `YOUTUBE_CHECK_INTERVAL_DAYS=1`

## Checkpoint (2026-07-18, продолжение) — SoundCloud-источники с автопроверкой

- **SoundCloud-ссылка = постоянный источник** (запрос владельца «я часто делаю новые биты»): таблица `soundcloud_sources` (миграция `c0d1e2f3a4b6`), [soundcloud_sources.py](app/services/soundcloud_sources.py) (add с дедупом по url + реактивация, mark_checked, sources_due_for_check). Ссылка в «Загрузить минус» теперь сохраняется источником и сканится ежедневно; дедуп импорта делает скан инкрементальным
- Celery: `youtube.soundcloud_scan_source` (ручной запуск — отчёт всегда; автоскан пишет первому админу только когда есть новое), `youtube.soundcloud_scan_due`. Ежедневный таймер `tg-music-youtube-scan` (CLI `youtube scan-due`) теперь дёргает и SoundCloud — отдельный юнит не нужен
- Интервал: `SOUNDCLOUD_CHECK_INTERVAL_DAYS` (дефолт 1). На VPS в `.env` добавлен `YOUTUBE_CHECK_INTERVAL_DAYS=1` — YouTube-источники владельца тоже проверяются ежедневно (было 30 дней)
- Тесты: **186 passed** (+2: дедуп/реактивация источника, due-выборка)

## Checkpoint (2026-07-18) — парсеры минусов (ТГ-канал, SoundCloud) + YouTube Music

- **ТГ-канал → минусы**: у `telegram_channel_sources` появился `target` (tracks|instrumentals, миграция `b9c0d1e2f3a5`). Источник с `target=instrumentals` кладёт аудио в базу минусов: [importer.py](app/services/telegram_channel/importer.py) ветвится на `import_instrumental_via_telegram_mint` ([catalog_import.py](app/services/catalog_import.py) — зеркало трекового минта: дедуп по отпечатку/метаданным только среди instrumentals, минт tg_file_id через бота, байты не на диске). Добавить канал: `python -m app.cli.telegram_channel add @zvyagaminus --instrumental`
- **SoundCloud → минусы (админ)**: мастер «Загрузить минус» принимает ссылку на SoundCloud (трек/профиль/сет). [soundcloud.py](app/services/soundcloud.py) (yt-dlp: разбор ссылки, список entries, скачивание + uploader), [soundcloud_import.py](app/services/soundcloud_import.py) (пачка ≤ playlist_import_limit, фильтр длительности 40с-9мин, artist из uploader/parse_title, отчёт). Celery-задача `youtube.soundcloud_minus_import` в очереди `youtube` — по завершении админу приходит отчёт (импортировано/дубли/ошибки). Без брокера — честный отказ
- **YouTube Music**: одиночные watch-ссылки работали и раньше (regex ловит music.youtube); `normalize_source_url` теперь приводит `music.youtube.com` → `www.youtube.com` (плейлисты/каналы для yt-dlp), подсказки мастера загрузки упоминают YouTube Music
- Тесты: **184 passed** (+10: test_soundcloud, test_instrumental_mint, importer target, YT Music ссылки)
- ⏳ Владелец сам добавляет: свой канал минусов через CLI (`--instrumental`), SoundCloud-ссылку — в админке «Загрузить минус». На VPS должен работать воркер очереди `youtube` (tg-music-youtube) для SoundCloud и воркер telegram-channel для канала

## Checkpoint (2026-07-17, вторая ночь) — большое ТЗ на редизайн 2.0 (26 разделов)

- **Навигация переписана** ([state.js](miniapp/src/state.js)): стек экранов `navigateTo/goBack/resetToTab` — «Назад» всегда ведёт туда, откуда пришли, с восстановлением позиции скролла (ТЗ §3-4). Все `data-action="nav" data-screen=…` на вложенных экранах заменены на `data-action="back"`
- **Нижний док** (main.js + components.css): мини-плеер и навигация в одном fixed `.bottom-dock` колонкой — наложения исключены; отступы `.screen` через классы `has-nav`/`is-playing` на #app (ТЗ §2)
- **Мои треки** ([mytracks.js](miniapp/src/screens/mytracks.js), новый): вкладки Все/Скачанные, поиск (placeholder «Search»), Shuffle + шит сортировки (5 вариантов), режим редактирования с удалением. `/library` принимает `page_size` (грузим по 100)
- **Главная** (§1): плитки без «Загрузок», hero = «Слушать ТегаМикс» (рекомендации+настройки объединены), второй слайд «Мои треки»
- **Плеер** (§7): play 60px, мета слева + «+»/«…» справа, чипы Скачать/Текст/Поделиться, обложка ограничена 42dvh. Для минусов (id<0) — кнопки скрыты
- **Текст песни** (§8): открывается сразу (баг был: оверлей плеера закрывал экран — теперь closePlayer при открытии). Добавление/правка текста — только Premium
- **Скачать** (§9): `POST /tracks/{id}/send` → бот шлёт аудио в чат по tg_file_id ([telegram_send.py](app/services/telegram_send.py)); без tg_file_id — 409
- **Библиотека** (§10): точечное обновление кнопок «+»/«✓» без полного рендера (мерцание убрано); гард отрицательных id
- **Поиск** (§11): таблица `search_queries` (миграция `a8b9c0d1e2f4`), `POST /search/log` (только Enter/чип, не дебаунс) + `GET /search/popular` ([search_log.py](app/services/search_log.py)); фейковые «популярные из каталога» удалены
- **Исполнители** (§13-14): `GET /artists` с дедупом lower(trim(artist)) ([artists.py](app/services/artists.py)), тап → треки исполнителя; «Кураторы» убраны (куратор = исполнитель), «Онлайн-треки» удалены (§15)
- **Настройки/документы** (§16-21): секции по VK, «Поддержка Telegram», полноценные FAQ (10 вопросов)/политика (8 разделов)/лицензия (6)/«О приложении» с версией 2.0
- **Профиль** (§22): без «Друзей» и огромной кнопки, аватар из `photo_url`; **рефералка** (§23) — отдельный экран (шаги, награды 1→3д…100→навсегда, прогресс, копировать/пригласить)
- **Premium** (§24): экран тарифов 1/3/6/12 мес = 21/63/126/252 ₽ (год выделен); бэк: `plan_price_rub`, `months` в metadata ЮKassa → `activate_premium(months=…)`
- **Плейлисты** (§6): VK-строки + инлайн-создание (`POST /playlist`); страница подборки с hero (обложка, счётчик, длительность, Слушать/Перемешать)
- Проверено вживую в dev-браузере (API 8010 + `dev_server.py` no-cache на 5500): навигация/скролл/плеер/тарифы/поиск — DOM-проверками (скриншоты в окружении таймаутят), консоль чистая, 0px переполнения. **174 теста зелёные** (+7 новых)
- ⏳ Скрины владельца vk disignet/ учтены; сортировка «Мои плейлисты» и обложки из файлов — нет данных на бэке (обложек у треков нет вообще)

## Checkpoint (2026-07-17, поздняя ночь) — чистка палитры + инлайн-кнопка ✅ ЗАДЕПЛОЕНО

- **Остатки аметиста мимо токенов убраны**: `cover.js` (обложки треков были захардкожены фиолетовыми → VK-палитра: серая база + сине-розовый отсвет), `index.html` theme-color `#050507`→`#0f0f10`, 4 фиолетовых rgba в плеере/premium-иконке → токены
- **Кнопка входа в бота под инлайн-треками** ([inline.py](app/handlers/inline.py)): тап по «via @bot» бота НЕ открывает (Telegram лишь начинает новый инлайн-запрос) — поэтому под каждый трек цепляется `reply_markup` с кнопкой «🎧 Слушать в TG Music» по **реф-ссылке отправителя** (приглашённые + дни Premium идут тому, кто скинул трек). ⚠️ `is_personal=True` обязателен — в выдаче личная ссылка, кэшировать между пользователями нельзя. Без `BOT_USERNAME` кнопки просто нет
- **Проверка без браузера** (MCP-инструменты браузера отвалились): рендер всех 16 экранов + 4 компонентов в node со стабами `localStorage`/`location`/`window` — все без ошибок и без «undefined»; `node --check` на 29 модулях; сверка всех `data-action` с обработчиками. **Визуально владелец не смотрел**
- Тесты: **167 passed** (`test_inline.py` новый)
- ⏳ Инлайн всё ещё ждёт `/setinline` у @BotFather (`getMe.supports_inline_queries: false`)

## Checkpoint (2026-07-17, ночь) — редизайн под VK Music ✅ ЗАДЕПЛОЕНО

- **Новая палитра** ([tokens.css](miniapp/src/styles/tokens.css)): почти чёрный `#0f0f10`, серые карточки `#202022`, цвет только в акцентах — сине-розовый градиент hero, синяя карточка подписки (`#2e55f2→#4a7bfb`), синий интерактив `#3b7bfe`. Имена токенов сохранены с «аметиста» — компонентные стили не трогали
- **Тема одна (тёмная)**: светлая тема, `data-theme`, `toggleTheme`, переключатель в настройках — удалены
- **Главная** ([home.js](miniapp/src/screens/home.js)) по референсам `disigner/`: hero-микс 320px со свайпом (белая круглая Play, «Настроить» внутри слайда рекомендаций, подсказка «Свайпните — другой микс»), карточка подписки, плитки 2×2 (Мои треки / Недавние / Плейлисты / Загрузки — иконка в правом нижнем углу)
- **Списки треков с главной удалены навсегда** (решение владельца) — вместе с приветствием, блоками «Новое в базе»/«Рекомендации»
- **[NEWS.md](NEWS.md)**: 5 готовых постов + шаблон. Правило «после каждого деплоя — пост» вынесено в раздел «Правило релизов»
- ⚠️ **Не проверено визуально**: браузерные MCP-инструменты отвалились в этой сессии. Проверено статически: синтаксис всех 29 JS-модулей (`node --check`), рендер home.js в node (3 слайда, 4 плитки, нет track-row), все `data-action` имеют обработчики, нет битых CSS-переменных. **Владельцу нужно глянуть глазами**
- ⚠️ **keybest.cc в чёрном списке Google Safe Browsing** → Safari на iOS показывает «Deceptive Website Warning» вместо Mini App. Инструкция по снятию — ниже в «Известные грабли»

## Checkpoint (2026-07-17, вечер) — каналы подписки из админки ✅ ЗАДЕПЛОЕНО

- **Обязательные подписки управляются из админки**: таблица `required_channels` (миграция `f6a7b8c9d0e2` посеяла @tgramuzuka + @zvyagaminus из .env — прод не заметил перехода). `/admin` → «📢 Каналы подписки»: список, 🗑 удаление (чистит кэш проверок канала), ➕ добавление (FSM: канал @username/-100…/t.me-ссылка → текст кнопки; живая валидация `check_channel_membership` — если бот не админ канала, добавление отклоняется с объяснением)
- **Пустой список каналов = гейт выключен** (бот доступен без подписки) — так админ может отключить подписку целиком
- `is_fully_subscribed` и гейт-клавиатура читают БД; env-поля `required_channel_*` остались только как сид миграции. Приватные каналы (-100…) в гейте без кнопки-ссылки (нет username)
- Кросс-постинг в ВК: код на проде, но **отложен по решению владельца** — env не настраиваем
- Тесты: 165 passed (`test_required_channels.py` новый; `test_subscription_service.py` переведён на БД)

## Checkpoint (2026-07-17) — плейлисты, минусы в Mini App, инлайн, кросс-пост ВК

- **Импорт плейлистов/каналов целиком** (только Premium, до `playlist_import_limit`=50 видео): ссылка на плейлист/канал в мастере загрузки → `is_playlist_link` → `list_videos` → пачка `youtube.user_import(quiet=True)` — треки тихо падают в библиотеку, одно сообщение «принято N». Watch-ссылка с `list=` считается одиночным видео (extract_video_id проверяется раньше)
- **Минусы в Mini App**: вкладки «Треки / 🎼 Минусы» в поиске (`state.searchMode`), `GET /instrumentals?q=&page_size=` теперь отдаёт Page[TrackOut] с отрицательными id + подписанным audio_url. У минусов нет кнопок «+»/шита (trackRow: id<0). ⚠️ Грабля: `cover.js` падал на отрицательных id (`-1 % 6 === -1` в JS) — исправлено Math.abs
- **Инлайн-режим** (`handlers/inline.py`): @бот <запрос> в любом чате → до 10 треков + 5 минусов по tg_file_id (мгновенно), пустой запрос → свежие треки; кнопка «Открыть TG Music» под выдачей. Вне гейта подписки (middleware только message/callback). **Требуется включить у BotFather: /setinline**
- **Кросс-пост ТГ→ВК** (`services/crosspost.py` + `handlers/news.py`): пост в новостном канале (бот — админ) → wall.post в группу ВК + ссылка на оригинал. Конфиг: `NEWS_CHANNEL_ID`, `VK_TOKEN` (токен сообщества с правом wall), `VK_GROUP_ID` (без минуса). Не настроено → молчит. **Ждём от владельца: id канала + бот-админ + ВК-токен**
- Тесты: 161 passed (`test_user_import.py` дополнен is_playlist_link)

## Checkpoint (2026-07-16, поздно) — парсер в общий доступ + очистка не-музыки

- **Импорт по YouTube-ссылке для всех пользователей**: мастер «Загрузить трек» принимает и ссылку (youtu.be / watch?v= / shorts / music.youtube / embed). Фильтры против мусора: только одиночное видео (не стрим), длительность `track_min_seconds..track_max_seconds` (40 сек – 9 мин, проверка ДО скачивания по метаданным и ПОСЛЕ по факту), лимит бесплатного тарифа = лимит загрузок (`can_upload`, импорт создаёт `Upload`), размер ≤ `max_file_size_mb`, дедуп по отпечатку. Поток: handler (`process_link` в upload.py) → `fetch_video_info` (yt-dlp skip_download, в `asyncio.to_thread`) → Celery `youtube.user_import` (очередь `youtube`, 2 ретрая по 60 сек) → mint через бота → трек приходит пользователю в чат + в его библиотеку. Без брокера — честное «импорт недоступен». Сервис: `app/services/youtube/user_import.py`
- **Очистка не-музыки**: `app/services/catalog_cleanup.py` (count/list/delete; удаляет файл из хранилища + user_library/playlist_tracks/track_events/lyrics/uploads, обнуляет track_id в youtube_imports/telegram_channel_imports, затем трек). В админке: строка «🗑 Не похоже на музыку: N» + кнопка → превью списка (топ-15 по длительности) → подтверждение → удаление. Инвариант «трек не удаляется» получил явное исключение (см. Инварианты)
- Тесты: `test_user_import.py` (разбор ссылок, границы), `test_catalog_cleanup.py` (счёт/удаление со связями/no-op). **160 passed**

## Checkpoint (2026-07-16) — ВСЁ ЗАДЕПЛОЕНО на прод

Весь редизайн + геймификация + тексты + офлайн + рекомендации/плейлисты/альбомы **задеплоены на keybest.cc** (коммиты `fbb6948`, `1f68c7a`). 152 теста зелёные.

- **Движок рекомендаций** ([recommendations.py](app/services/recommendations.py)): `GET /mix?mood=&recognizability=&language=` — язык выводится из текста (кириллица→русская), настроение по `Track.mood` (мягкий фильтр), тип по прослушиваниям/дате. «Применить» в настройках рекомендаций играет персональный микс. Настроение трека тегирует админ (шаг в `ta:edit`). Миграция `e5a6b7c8d9f0` (Track.mood)
- **Плейлисты/Альбомы**: `GET /playlists`, `/playlists/{id}/tracks`, `/albums`, `/albums/tracks?name=` — реальные данные (альбомы из `Track.album`). Экраны `playlists.js`/`albums.js`/`collection.js`. Кураторы — честный пустой экран (данных нет), «soon»-тостов больше нет
- **Бот**: меню = Плеер / Загрузить трек / Купить Premium; админ-статистика упрощена (активные за всё время; убраны прослушивания/скачивания/популярные/загрузки/плейлисты)
- **Деплой выполнен**: 3 миграции применены (prod был `b2d3e4f5a6c7` → `e5a6b7c8d9f0`), перезапущены `tg-music-{bot,worker,api,youtube}` (все active), бот на polling, API отдаёт 200 реальному трафику
- **nginx**: в `location /` добавлен `add_header Cache-Control "no-cache"` ([deploy/nginx-keybest.conf](deploy/nginx-keybest.conf) + живой конфиг) — вернувшиеся пользователи ревалидируют и получают свежий Mini App (проверено: заголовок отдаётся на index.html и *.js). Бэкапы конфига — в `/root/nginx-backups`
- **`aiohttp`** добавлен в requirements.txt (использует ЮKassa + LRCLIB)
- **Доделано (2026-07-16, вторая волна):**
  - **«Инструментальная» в миксе**: `GET /mix?language=instrumental` отдаёт минусы из `instrumentals` с **отрицательными id** (не пересекаются с треками) и `audio_url` на новый эндпоинт `GET /instrumentals/{id}/audio` (HMAC-подпись в отдельном namespace `ins:` — подпись трека не подходит, проверено 403; Range поддержан). Фронт не пишет listen для id<0
  - **Кураторы**: без новой модели — кураторские подборки = плейлисты пользователей из `ADMIN_IDS` (`GET /curators`, `/curators/{id}/tracks`, пустые скрыты). Экран `curators.js` → collection. Чтобы наполнить: админ создаёт плейлист в Mini App
  - **Массовое тегирование настроения**: `python -m app.cli.set_mood <mood> <запрос>` / `--untagged` / `--dry`
- **Осталось честно недоделанным:** формат минусов в стриминге захардкожен mp3 (в `instrumentals` нет поля format); кураторские подборки показываются все (нет флага «черновик»)

## Checkpoint (2026-07-14, вечер) — редизайн Mini App: блоки B/C/D ЗАВЕРШЕНЫ

Все 4 блока большого ТЗ сделаны (A UI ✅, B геймификация ✅, C тексты ✅, D офлайн ✅). **147 тестов зелёные**, консоль без ошибок, проверено end-to-end в dev-браузере.

- **Блок B — Геймификация** (бэк + фронт):
  - Модель: `User.referred_by / referral_milestones_claimed / premium_discount_pct` (миграция `c3e4f5a6b7d8`)
  - `services/gamification.py`: ранги Bronze→Legend, реферальные Premium-награды (1→3д … 100→пожизненно, идемпотентно), 16 достижений (прослушивания/часы/серия дней/избранное/плейлисты/Premium/приглашённые), скидка 50% пригласившему
  - `/start ref_<id>` привязывает нового пользователя (handlers/start.py); скидка вшита в оплату ЮKassa (эффективная цена + сброс)
  - API: `GET /profile` (ранг/прогресс/статы/достижения/реф-ссылка), `POST /tracks/{id}/listen` (Mini App пишет прослушивания)
  - Фронт: профиль (ранг у имени, прогресс-бар, 4 стата, «Пригласить друга» через tg share, превью достижений) + экран `achievements.js` (по категориям, locked/unlocked, прогресс). `tests/test_gamification.py` (7)
- **Блок C — Тексты песен** (бэк + фронт):
  - Модель `Lyrics` (миграция `d4f5a6b7c8e9`); `services/lyrics.py`: автопоиск LRCLIB (свободный API, graceful-фолбэк) + ручное добавление пользователями
  - API: `GET/POST /tracks/{id}/lyrics`; фронт: экран `lyrics.js` (просмотр + редактор), вход из шита трека «Текст песни». `tests/test_lyrics_service.py` (3)
- **Блок D — Офлайн-кэш Premium** (только фронт): `offline.js` (Cache API + localStorage-индекс), сохранение/удаление трека, воспроизведение из blob без сети (проверено: повторный запуск не даёт сетевого запроса), экран «Загрузки», пункт «Сохранить офлайн» в шите (только Premium)
- **⚠️ dev-нюансы:** dev-JWT истекает (~сутки) — перегенерировать: `create_access_token(5852263277)`; кэш ES-модулей (см. [[miniapp-dev-module-cache]]) — warm+navigate после правок; scratchpad `nocache_server.py` не переживает рестарт сессии (пересоздавать). **Не задеплоено**
- **Осталось честно недоделанным:** серверная фильтрация микса под настроение/язык (настройки сохраняются локально, движок рекомендаций — отдельная задача); плейлисты/альбомы/кураторы в «Ещё» (тост «soon»); бот-сторона реферальной ссылки (Mini App-профиль покрывает)

## Checkpoint (2026-07-14) — редизайн Mini App, блок A ЗАВЕРШЁН

- **Большое ТЗ на редизайн** (референсы VK в `kreen/`, эскизы в `MiniAppPhoto/`) разбито на 4 блока: **A** UI-редизайн ✅, **B** геймификация (рефералы/уровни/достижения — нужны новые модели+миграции), **C** тексты песен (источник: LRCLIB + ручное добавление юзерами), **D** офлайн-кэш Premium.
- **Блок A полностью сделан и проверен в dev-браузере (DOM-верификация всех экранов, 0px горизонт. переполнения, консоль без ошибок):**
  - `prefs.js` — localStorage: недавние треки (с `audio_url`), недавние запросы, настройки рекомендаций, любимые исполнители
  - **Главная** (`screens/home.js`): swipe-hero карусель миксов (`play-mix`: catalog/library/discover, scroll-snap+точки), блок «Рекомендации»+«Настроить», карточка подписки (не-Premium, `dismiss-sub`), быстрый доступ, редизайн списка
  - **Поиск** (`screens/search.js`): убран «Популярное сейчас», добавлены «Популярные запросы» (артисты из базы) + «Недавние запросы» (Enter/чип сохраняют, Очистить)
  - **Библиотека** (`screens/library.js`): «Мои треки» блоками по 3 со свайпом (`.lib-cols`), кнопки Мой микс/Любимые/Рекомендации, раздел «Ещё» (Premium-карточка + 7 плиток; без данных → тост «soon»)
  - **Настройки** (`screens/settings.js`): разделы Интерфейс/Предпочтения/Помощь/Документы
  - Новые экраны: `recommendations.js` (настроение×5/тип×3/язык×3), `recent.js`, `artists.js` (избранные исполнители из базы, toggle), `docs.js` (FAQ/политика/лицензия/о приложении — общий по ключу `docKey`)
  - `state.js`: `playMix()`, `pushRecentTrack` на старте трека, `recDraft`, `docKey`, `subDismissed`, класс `is-playing` на #app
  - Адаптивность (`base.css`): `.h-scroll` (ленты не двигают страницу), планшетный max-width 560, отступ под мини-плеер; токены радиусов/отступов/высот
  - Жест **свайп-вниз** (`main.js` touchstart/touchend) закрывает вложенные страницы/плеер/шит
- **Осталось для полной готовности блока A:** живой скриншот-пруф (капчур в этом окружении подвисает — проверено через DOM); мелкая полировка (сохранение scroll при ре-рендере — `root.innerHTML` сбрасывает позицию при play/pause). **Не задеплоено** — только dev.
- **Осталось честно недоделанным (требует бэкенда, блоки B-D):** серверная фильтрация микса под настроение/язык; плейлисты/альбомы/кураторы/загрузки/онлайн в «Ещё» (тост «soon»)
- **Dev-стенд:** API :8010 (preview `api`) + статика :5500. ⚠️ Из-за агрессивного кэша ES-модулей в dev-браузере нужен no-cache сервер: `scratchpad/nocache_server.py` (Cache-Control: no-store) на 5500 вместо launch-конфига `miniapp`, иначе правки не подхватываются. Вход — dev-JWT в `localStorage["tgmusic-dev-token"]`

## Checkpoint (2026-07-13, вечер)

- **Задеплоено и работает:** Mini App на https://keybest.cc целиком (коммит 1929c02):
  1. DNS прописан пользователем → certbot выпустил сертификат (Let's Encrypt, автопродление)
  2. nginx-сайт keybest.cc: статика Mini App + `/api/` + `/webhook/` → uvicorn :8010
  3. `tg-music-api.service` активен (`systemctl status tg-music-api`)
  4. `.env` на VPS дополнен: `PUBLIC_BASE_URL`, `BOT_USERNAME`, `API_CORS_ORIGINS`, `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`
  5. Бот перезапущен — кнопка «🎧 Открыть плеер» первая в главном меню
  6. Smoke-тесты через curl прошли: статика 200, `/api/login` без initData → 401, `/webhook/yookassa` без валидного тела → 400
- Что внутри (см. предыдущий срез): аудио-стриминг по HMAC-подписи с Range, ЮKassa redirect-оплата 21 ₽ с перепроверкой статуса у API (не доверяем телу webhook), Mini App на реальных данных без моков (initData→JWT), настоящий `<audio>` с автопереключением по `ended`, прогресс через отдельный канал подписки (не полный re-render на тик — было источником лагов), вкладки Текст/Отзыв удалены
- ⚠️ **Секретный ключ ЮKassa засветился в чате пользователя** — сейчас на сервере рабочий (боевой) ключ из переписки; после подтверждения что всё работает — перевыпустить в ЛК ЮKassa и обновить `.env` на VPS
- Не проверено вживую (нужен реальный Telegram-клиент — sandbox блокирует переход на внешний домен): открытие Mini App из бота, автоплей в реальных условиях, прохождение оплаты 21 ₽ до конца (webhook → activate_premium)
- Dev-стенд для локальной отладки Mini App: см. miniapp/README.md (dev_miniapp.db + WAV-сиды + dev-JWT в localStorage)
