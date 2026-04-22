"""Unit tests for the RefreshToken model structure (PRD-4 schema requirements)."""

from typing import Any

import pytest
import sqlalchemy as sa

from app.models.refresh_token import RefreshToken


class TestRefreshTokenModelStructure:
    def test_tablename(self) -> None:
        assert RefreshToken.__tablename__ == "refresh_tokens"

    def test_primary_key_is_id(self) -> None:
        table: Any = RefreshToken.__table__
        pk_col_names = {c.name for c in table.primary_key}
        assert pk_col_names == {"id"}

    def test_token_hash_is_unique(self) -> None:
        table: Any = RefreshToken.__table__
        col = table.c["token_hash"]
        # Either column-level unique=True or a UniqueConstraint covers this
        unique_via_col = col.unique is True
        unique_via_constraint = any(
            isinstance(c, sa.UniqueConstraint) and set(c.columns.keys()) == {"token_hash"}
            for c in table.constraints
        )
        assert unique_via_col or unique_via_constraint

    def test_family_id_indexed(self) -> None:
        table: Any = RefreshToken.__table__
        index_cols = {
            frozenset(idx.columns.keys())
            for idx in table.indexes
        }
        assert frozenset({"family_id"}) in index_cols

    def test_token_hash_indexed(self) -> None:
        table: Any = RefreshToken.__table__
        index_cols = {
            frozenset(idx.columns.keys())
            for idx in table.indexes
        }
        assert frozenset({"token_hash"}) in index_cols

    def test_required_columns_exist(self) -> None:
        table: Any = RefreshToken.__table__
        col_names = set(table.c.keys())
        required = {"id", "family_id", "user_id", "token_hash", "parent_token_id",
                    "issued_at", "expires_at", "revoked_at"}
        assert required <= col_names

    def test_revoked_at_is_nullable(self) -> None:
        table: Any = RefreshToken.__table__
        assert table.c["revoked_at"].nullable is True

    def test_parent_token_id_is_nullable(self) -> None:
        table: Any = RefreshToken.__table__
        assert table.c["parent_token_id"].nullable is True

    def test_user_id_fk_to_users(self) -> None:
        table: Any = RefreshToken.__table__
        fk_targets = {
            fk.target_fullname
            for col in table.c
            for fk in col.foreign_keys
            if col.name == "user_id"
        }
        assert "users.id" in fk_targets

    def test_parent_token_id_fk_to_self(self) -> None:
        table: Any = RefreshToken.__table__
        fk_targets = {
            fk.target_fullname
            for col in table.c
            for fk in col.foreign_keys
            if col.name == "parent_token_id"
        }
        assert "refresh_tokens.id" in fk_targets


class TestRefreshTokenDefaults:
    def test_id_column_has_callable_default(self) -> None:
        table: Any = RefreshToken.__table__
        # column default fires at INSERT time (not Python instantiation)
        col_default = table.c["id"].default
        assert col_default is not None
        assert col_default.is_callable

    def test_revoked_at_defaults_to_none(self) -> None:
        rt = RefreshToken(
            family_id=None,  # type: ignore[arg-type]
            user_id=None,  # type: ignore[arg-type]
            token_hash="x",
            issued_at=None,  # type: ignore[arg-type]
            expires_at=None,  # type: ignore[arg-type]
        )
        assert rt.revoked_at is None

    def test_parent_token_id_defaults_to_none(self) -> None:
        rt = RefreshToken(
            family_id=None,  # type: ignore[arg-type]
            user_id=None,  # type: ignore[arg-type]
            token_hash="x",
            issued_at=None,  # type: ignore[arg-type]
            expires_at=None,  # type: ignore[arg-type]
        )
        assert rt.parent_token_id is None
