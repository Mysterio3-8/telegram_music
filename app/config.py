from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    database_url: str = "sqlite+aiosqlite:///music_bot.db"
    page_size: int = 5
    library_search_limit: int = 10
    max_file_size_mb: int = 50

    # Premium (SPEC §14)
    premium_price_stars: int = 15
    premium_price_rub: int = 17
    premium_duration_days: int = 30
    payment_provider_token: str = ""  # токен провайдера для карты/СБП; пусто → доступны только Stars

    # Лимиты бесплатного тарифа (Premium снимает)
    free_playlist_limit: int = 5
    free_upload_limit: int = 10

    # Реклама (SPEC §24): показ после каждого N-го действия бесплатного пользователя
    ad_frequency: int = 10

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

    @property
    def effective_celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url


settings = Settings()
