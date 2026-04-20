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
        if v.startswith("postgresql+psycopg://"):
            return v.replace("postgresql+psycopg://", "postgresql+psycopg_async://", 1)
        if v.startswith("postgresql+psycopg_async://"):
            return v
        raise ValueError(
            "DATABASE_URL must use postgresql+psycopg:// or postgresql+psycopg_async://; "
            f"got: {v!r}"
        )


settings = Settings()
