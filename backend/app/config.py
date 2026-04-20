from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = (
        "postgresql+psycopg_async://shared_todos:shared_todos@localhost:5432/shared_todos"
    )
    smtp_host: str = "localhost"
    smtp_port: int = 1025


settings = Settings()
