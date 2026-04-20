from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="forbid")

    database_url: str
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)

    # Session signing — must be set in production; dev default is only for local/CI
    secret_key: str = "dev-secret-key-change-in-production"
    session_ttl_days: int = Field(default=7, ge=1, le=365)

    # Rate limiting: login attempts per IP per window
    rate_limit_login_attempts: int = Field(default=10, ge=1)
    rate_limit_login_window_seconds: int = Field(default=900, ge=1)  # 15 min

    # Google OAuth — optional for dev; required for OAuth feature
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/oauth/google/callback"

    # Frontend base URL for post-OAuth redirect
    frontend_url: str = "http://localhost:3000"

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
