"""Structural tests for List, Item, Share models — no DB required."""

from typing import Any

import sqlalchemy as sa

from app.models.item import Item
from app.models.list_ import List
from app.models.share import Share


def _col(model: type, name: str) -> Any:
    return model.__table__.c[name]  # type: ignore[attr-defined]


class TestListModel:
    def test_has_id_uuid(self) -> None:
        col = _col(List, "id")
        assert isinstance(col.type, sa.Uuid)

    def test_has_name(self) -> None:
        col = _col(List, "name")
        assert isinstance(col.type, sa.String)

    def test_owner_id_fk(self) -> None:
        col = _col(List, "owner_id")
        assert len(col.foreign_keys) == 1

    def test_created_at_timezone(self) -> None:
        col = _col(List, "created_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone

    def test_updated_at_timezone(self) -> None:
        col = _col(List, "updated_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone


class TestItemModel:
    def test_has_id_uuid(self) -> None:
        col = _col(Item, "id")
        assert isinstance(col.type, sa.Uuid)

    def test_list_id_fk(self) -> None:
        col = _col(Item, "list_id")
        assert len(col.foreign_keys) == 1

    def test_has_content(self) -> None:
        col = _col(Item, "content")
        assert isinstance(col.type, sa.Text)

    def test_completed_bool(self) -> None:
        col = _col(Item, "completed")
        assert isinstance(col.type, sa.Boolean)

    def test_order_int(self) -> None:
        col = _col(Item, "order")
        assert isinstance(col.type, sa.Integer)

    def test_created_at_timezone(self) -> None:
        col = _col(Item, "created_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone

    def test_updated_at_timezone(self) -> None:
        col = _col(Item, "updated_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone


class TestShareModel:
    def test_list_id_fk(self) -> None:
        col = _col(Share, "list_id")
        assert len(col.foreign_keys) == 1

    def test_user_id_fk(self) -> None:
        col = _col(Share, "user_id")
        assert len(col.foreign_keys) == 1

    def test_role_string(self) -> None:
        col = _col(Share, "role")
        assert isinstance(col.type, sa.String)

    def test_granted_at_timezone(self) -> None:
        col = _col(Share, "granted_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone

    def test_role_check_constraint_exists(self) -> None:
        constraint_names = {c.name for c in Share.__table__.constraints}  # type: ignore[attr-defined]
        assert any("role_valid" in (n or "") for n in constraint_names)

    def test_composite_pk_enforces_uniqueness(self) -> None:
        # Uniqueness of (list_id, user_id) is guaranteed by the composite PK,
        # not a separate UniqueConstraint (which would create a redundant index).
        table: Any = Share.__table__
        pk_col_names = {c.name for c in table.primary_key}
        assert pk_col_names == {"list_id", "user_id"}, (
            "Share composite PK must include exactly list_id and user_id"
        )
