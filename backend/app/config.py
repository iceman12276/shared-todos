from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET_KEY = "dev-secret-key-change-in-production"  # noqa: S105
_MIN_SECRET_KEY_LEN = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="forbid")

    database_url: str
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, ge=1, le=65535)

    # Session signing — must be set in production; dev default is only for local/CI
    secret_key: str = _DEV_SECRET_KEY
    session_ttl_days: int = Field(default=7, ge=1, le=365)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=365)

    # Rate limiting: login attempts per IP per window
    rate_limit_login_attempts: int = Field(default=10, ge=1)
    rate_limit_login_window_seconds: int = Field(default=900, ge=1)  # 15 min

    # Google OAuth — optional for dev; required for OAuth feature
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/oauth/google/callback"

    # Frontend base URL for post-OAuth redirect
    frontend_url: str = "http://localhost:3000"

    # Set True in production (HTTPS). Dev/CI default is False (HTTP only).
    cookie_secure: bool = False

    # Set True when running behind a trusted reverse proxy that sets X-Forwarded-For.
    # Keep False (default) for direct connections — trusting XFF unconditionally
    # allows IP spoofing by clients that set the header themselves.
    trust_proxy: bool = False

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

    @model_validator(mode="after")
    def require_secure_secrets_in_production(self) -> "Settings":
        """Mirror the database_url fail-fast pattern for auth secrets.

        When cookie_secure=True (production HTTPS context), insecure defaults
        for secret_key, google_client_id, and google_client_secret must not
        be accepted — they would silently break OAuth CSRF protection and
        OAuth login respectively.
        """
        if not self.cookie_secure:
            return self

        errors: list[str] = []

        if self.secret_key == _DEV_SECRET_KEY or len(self.secret_key) < _MIN_SECRET_KEY_LEN:
            errors.append(
                f"secret_key must be a random string of at least {_MIN_SECRET_KEY_LEN} "
                "characters when cookie_secure=True (production); got the dev default or "
                "a value that is too short"
            )

        if not self.google_client_id:
            errors.append("google_client_id must be set when cookie_secure=True (production)")

        if not self.google_client_secret:
            errors.append("google_client_secret must be set when cookie_secure=True (production)")

        if errors:
            raise ValueError("; ".join(errors))

        return self


settings = Settings()
