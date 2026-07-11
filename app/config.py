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


settings = Settings()
