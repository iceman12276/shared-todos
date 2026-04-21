"""Lightweight structural tests — verify model columns without hitting the DB."""

from typing import Any

import sqlalchemy as sa

from app.models.password_reset_token import PasswordResetToken
from app.models.session import Session
from app.models.user import User


def _col(model: type, name: str) -> Any:
    return model.__table__.c[name]  # type: ignore[attr-defined]


class TestUserModel:
    def test_has_id_uuid(self) -> None:
        col = _col(User, "id")
        assert isinstance(col.type, sa.Uuid)

    def test_has_email(self) -> None:
        col = _col(User, "email")
        assert isinstance(col.type, sa.String)
        assert col.unique

    def test_password_hash_nullable(self) -> None:
        col = _col(User, "password_hash")
        assert col.nullable

    def test_google_sub_nullable(self) -> None:
        col = _col(User, "google_sub")
        assert col.nullable

    def test_created_at_timezone(self) -> None:
        col = _col(User, "created_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone

    def test_updated_at_timezone(self) -> None:
        col = _col(User, "updated_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone


class TestSessionModel:
    def test_has_id_uuid(self) -> None:
        col = _col(Session, "id")
        assert isinstance(col.type, sa.Uuid)

    def test_token_hash_unique(self) -> None:
        col = _col(Session, "token_hash")
        assert col.unique

    def test_user_id_fk(self) -> None:
        col = _col(Session, "user_id")
        assert len(col.foreign_keys) == 1

    def test_expires_at_timezone(self) -> None:
        col = _col(Session, "expires_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone


class TestPasswordResetTokenModel:
    def test_has_id_uuid(self) -> None:
        col = _col(PasswordResetToken, "id")
        assert isinstance(col.type, sa.Uuid)

    def test_token_hash_unique(self) -> None:
        col = _col(PasswordResetToken, "token_hash")
        assert col.unique

    def test_user_id_fk(self) -> None:
        col = _col(PasswordResetToken, "user_id")
        assert len(col.foreign_keys) == 1

    def test_used_at_nullable(self) -> None:
        col = _col(PasswordResetToken, "used_at")
        assert col.nullable

    def test_expires_at_timezone(self) -> None:
        col = _col(PasswordResetToken, "expires_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone
