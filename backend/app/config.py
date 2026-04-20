from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="forbid")

    database_url: str
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)

    @field_validator("database_url")
    @classmethod
    def normalize_db_dialect(cls, v: str) -> str:
        # CI sets postgresql+psycopg:// (psycopg3 sync); async engine needs psycopg_async.
        return v.replace("postgresql+psycopg://", "postgresql+psycopg_async://")


settings = Settings()
