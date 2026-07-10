from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    database_url: str = "sqlite+aiosqlite:///music_bot.db"
    page_size: int = 5
    library_search_limit: int = 10


settings = Settings()
