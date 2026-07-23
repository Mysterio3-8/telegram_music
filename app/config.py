from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    bot_username: str = "tgram_music_bot"  # для return_url ЮKassa и ссылок «поделиться»
    database_url: str = "sqlite+aiosqlite:///music_bot.db"
    page_size: int = 5
    library_search_limit: int = 10
    max_file_size_mb: int = 50

    # Границы «похоже на музыку» (0 = лимит снят). Короче — джингл/обрезок,
    # длиннее — подкаст/видео. Используются в импорте по ссылке и в очистке базы.
    # Владелец снял ограничения по длительности — фильтр по времени выключен.
    track_min_seconds: int = 0
    track_max_seconds: int = 0
    # Импорт целого плейлиста/канала: максимум видео за раз (0 = без лимита)
    playlist_import_limit: int = 0

    # Premium (SPEC §14)
    premium_price_stars: int = 15
    premium_price_rub: int = 21
    premium_forever_price_rub: int = 10000  # тариф «навсегда»
    premium_duration_days: int = 30
    payment_provider_token: str = ""  # токен провайдера для карты/СБП; пусто → доступны только Stars

    # TON-оплата (крипта). Пусто → способ скрыт. Кошелёк владельца + опц. ключ toncenter.
    # Оплата: пользователь шлёт нужную сумму на адрес с уникальным комментарием (order id),
    # фоновая проверка через toncenter активирует Premium. Требует живого теста.
    ton_wallet_address: str = ""
    toncenter_api_key: str = ""
    ton_rub_per_ton: int = 0  # курс: сколько рублей в 1 TON (0 → TON-оплата выключена)

    # ЮKassa (API ЮKassa, redirect-сценарий) — оплата 21 ₽ картой/СБП вне Telegram Payments.
    # Пустые значения → кнопка оплаты через ЮKassa не показывается.
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""

    # Публичный базовый URL (https://keybest.cc) — подписанные аудио-ссылки Mini App
    # и return_url ЮKassa. Пусто → аудио-ссылки относительные (same-origin).
    public_base_url: str = ""

    # Кросс-пост новостей: пост в этом ТГ-канале (бот — админ) уходит в ВК.
    # Пустые значения → кросс-пост выключен, бот молчит.
    news_channel_id: int = 0
    vk_token: str = ""  # токен сообщества ВК с правом wall
    vk_group_id: int = 0  # положительный id группы (без минуса)

    # Лимиты бесплатного тарифа (Premium снимает; 0 = без лимита)
    free_playlist_limit: int = 5
    free_upload_limit: int = 0  # владелец снял лимит на количество загрузок

    # Реклама (SPEC §24): показ после каждого N-го действия бесплатного пользователя
    ad_frequency: int = 10

    # Администраторы (Telegram ID через запятую): /admin, правка метаданных треков
    admin_ids: str = ""

    # Обязательная подписка (TZ §14-17). Каналы живут в БД (таблица required_channels,
    # управление — из админки). Поля ниже — только сид для миграции f6a7b8c9d0e2.
    required_channel_1: str = "@tgramuzuka"
    required_channel_1_label: str = "📢 ТГ Музыка"
    required_channel_2: str = "@zvyagaminus"
    required_channel_2_label: str = "🎤 Минусы"
    subscription_cache_ttl_minutes: int = 60
    admin_bypass_subscription: bool = False

    @property
    def required_channels(self) -> list[tuple[str, str]]:
        """Сид-значения для миграции; рантайм читает таблицу required_channels."""
        pairs = [
            (self.required_channel_1, self.required_channel_1_label),
            (self.required_channel_2, self.required_channel_2_label),
        ]
        return [(channel, label) for channel, label in pairs if channel]

    # Очередь воспроизведения: сколько аудио отправляется одной пачкой
    # (Telegram-клиент сам проигрывает следующее аудио в чате — пачка = непрерывная очередь)
    queue_batch_size: int = 5

    # FSM-хранилище: Redis, если задан; иначе in-memory (теряется при рестарте)
    redis_url: str = ""

    # Фоновая обработка (Celery). Брокер по умолчанию — тот же Redis.
    celery_broker_url: str = ""

    # Хранилище аудиофайлов
    storage_dir: str = "storage"  # каталог для локального бэкенда
    s3_endpoint_url: str = ""  # если задан — используется S3-совместимое хранилище
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"

    # chromaprint: имя/путь бинарника fpcalc (пусто → отпечаток не считается)
    fpcalc_path: str = "fpcalc"

    # LRU-кэш байтов аудио для стриминга Mini App: горячие треки не скачиваются
    # из Telegram/S3 на каждый плей. 0 МБ → кэш выключен.
    audio_cache_dir: str = "audio_cache"
    audio_cache_max_mb: int = 2048
    # Архивная копия при минте пишется только если на диске остаётся больше
    # этого запаса (ГБ) — массовый импорт 24/7 не должен забить диск до отказа.
    # Трек без архива продолжает работать по tg_file_id. 0 = без проверки (S3).
    archive_min_free_gb: float = 2.0

    # YouTube-импортёр (доп. ТЗ). Cookies — путь к файлу в формате Netscape (yt-dlp),
    # НЕ в БД и НЕ в логах; для публичных каналов не требуются.
    youtube_cookies_path: str = ""
    youtube_audio_format: str = "bestaudio[ext=m4a]/bestaudio/best"
    youtube_concurrency: int = 2  # одновременных загрузок (§14): 1-5
    youtube_max_retries: int = 3  # попыток при временной ошибке (§13)
    youtube_check_interval_days: int = 30  # период автопроверки новых видео (§11)
    # SoundCloud-источники минусов: автопроверка новых битов (владелец публикует часто)
    soundcloud_check_interval_days: int = 1
    # Сколько треков забирать со страницы поиска/тега SoundCloud (scsearch<N>)
    soundcloud_search_limit: int = 200
    # Анти-бан при массовой закачке 24/7: рандомная пауза между скачиваниями (сек)
    soundcloud_min_delay: float = 5.0
    soundcloud_max_delay: float = 60.0
    # Прокси для SoundCloud-запросов yt-dlp: http/socks5-адреса через запятую
    # (http://user:pass@host:port). Пусто → без прокси. Ротация по кругу на каждый
    # запрос; при ошибке скачивания — повтор через следующий прокси.
    proxy_list: str = ""

    @property
    def proxy_list_items(self) -> list[str]:
        return [p.strip() for p in self.proxy_list.split(",") if p.strip()]

    # Личный Telegram-канал: импорт своих аудиопостов через MTProto (Telethon).
    # api_id/api_hash — на my.telegram.org. session_path — файл входа, вне git,
    # права 600 (даёт доступ к аккаунту как номер телефона). Создаётся один раз
    # через `python -m app.cli.telegram_login`, дальше используется без диалога.
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_session_path: str = "telegram_userbot.session"
    # Приватный чат, куда бот перезаливает трек, чтобы получить свой tg_file_id
    # (без него бот не может отправлять то, что скачал не сам userbot).
    # Пусто → используется личка первого администратора (ADMIN_IDS).
    telegram_archive_chat_id: int = 0
    telegram_channel_check_interval_days: int = 1
    telegram_channel_max_retries: int = 3

    @property
    def effective_archive_chat_id(self) -> int:
        if self.telegram_archive_chat_id:
            return self.telegram_archive_chat_id
        admins = sorted(self.admin_id_set)
        return admins[0] if admins else 0

    # Публичный API (§27)
    jwt_secret: str = ""  # пусто → подписываем bot_token
    jwt_ttl_minutes: int = 1440
    api_cors_origins: str = ""  # список origin через запятую для Mini App

    @property
    def effective_jwt_secret(self) -> str:
        return self.jwt_secret or self.bot_token

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def effective_celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def admin_id_set(self) -> set[int]:
        return {int(part) for part in self.admin_ids.split(",") if part.strip().isdigit()}


settings = Settings()
