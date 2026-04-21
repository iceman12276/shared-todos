"""Unit tests for Settings fail-fast validators (CRITICAL-3).

Verifies that secret_key, google_client_id, google_client_secret each
raise ValidationError when they carry the insecure default/empty value
while cookie_secure=True (production context).

Settings reads from the .env file at construction. We patch the env vars
directly so the validator sees our test values without touching .env.
"""

import os

import pytest
from pydantic import ValidationError


def _build_settings(**overrides: str | bool | int) -> object:
    """Build a Settings with the given overrides, bypassing .env."""
    env: dict[str, str] = {
        "DATABASE_URL": "postgresql+psycopg://u:p@localhost/db",
        "COOKIE_SECURE": "true",
        "SECRET_KEY": "a-secure-key-that-is-at-least-32-chars-long!",
        "GOOGLE_CLIENT_ID": "real-client-id",
        "GOOGLE_CLIENT_SECRET": "real-client-secret",
    }
    for k, v in overrides.items():
        env[k.upper()] = str(v)

    # Clear any existing env vars so .env file values don't bleed through
    backup = {k: os.environ.pop(k, None) for k in env}
    for k, v in env.items():
        os.environ[k] = v
    try:
        from app.config import Settings

        return Settings()
    finally:
        for k, original in backup.items():
            if original is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = original


def test_secret_key_default_rejected_in_prod() -> None:
    """Dev default secret_key must raise ValidationError when cookie_secure=True."""
    with pytest.raises(ValidationError, match="secret_key"):
        _build_settings(secret_key="dev-secret-key-change-in-production")  # noqa: S106


def test_secret_key_short_rejected_in_prod() -> None:
    """secret_key shorter than 32 chars must raise ValidationError in prod."""
    with pytest.raises(ValidationError, match="secret_key"):
        _build_settings(secret_key="tooshort")  # noqa: S106


def test_google_client_id_empty_rejected_in_prod() -> None:
    """Empty google_client_id must raise ValidationError when cookie_secure=True."""
    with pytest.raises(ValidationError, match="google_client_id"):
        _build_settings(google_client_id="")


def test_google_client_secret_empty_rejected_in_prod() -> None:
    """Empty google_client_secret must raise ValidationError when cookie_secure=True."""
    with pytest.raises(ValidationError, match="google_client_secret"):
        _build_settings(google_client_secret="")


def test_all_valid_in_prod_passes() -> None:
    """All required secrets set correctly must not raise."""
    result = _build_settings()
    assert result is not None


def test_dev_defaults_allowed_when_cookie_secure_false() -> None:
    """Dev defaults must be accepted when cookie_secure=False (local/CI)."""
    result = _build_settings(
        cookie_secure="false",
        secret_key="dev-secret-key-change-in-production",  # noqa: S106
        google_client_id="",
        google_client_secret="",
    )
    assert result is not None
