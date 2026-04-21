"""Unit tests for authz role-resolution logic."""

import pytest

from app.authz.permissions import can_perform, effective_role


class TestEffectiveRole:
    def test_owner_role_is_owner(self) -> None:
        assert effective_role(is_owner=True, share_role=None) == "owner"

    def test_share_editor_role(self) -> None:
        assert effective_role(is_owner=False, share_role="editor") == "editor"

    def test_share_viewer_role(self) -> None:
        assert effective_role(is_owner=False, share_role="viewer") == "viewer"

    def test_no_access_is_none(self) -> None:
        assert effective_role(is_owner=False, share_role=None) is None

    def test_owner_overrides_share(self) -> None:
        # Owner who also has a share row (shouldn't happen, but be safe)
        assert effective_role(is_owner=True, share_role="viewer") == "owner"


class TestCanPerform:
    def test_owner_can_do_everything(self) -> None:
        actions = [
            "read_list",
            "list_items",
            "create_item",
            "update_item",
            "delete_item",
            "rename_list",
            "share_list",
            "change_collaborator_role",
            "revoke_share",
            "delete_list",
        ]
        for action in actions:
            assert can_perform("owner", action), f"owner should be able to {action}"

    def test_editor_can_read_and_item_crud(self) -> None:
        assert can_perform("editor", "read_list")
        assert can_perform("editor", "list_items")
        assert can_perform("editor", "create_item")
        assert can_perform("editor", "update_item")
        assert can_perform("editor", "delete_item")

    def test_editor_cannot_manage_list_or_shares(self) -> None:
        assert not can_perform("editor", "rename_list")
        assert not can_perform("editor", "share_list")
        assert not can_perform("editor", "change_collaborator_role")
        assert not can_perform("editor", "revoke_share")
        assert not can_perform("editor", "delete_list")

    def test_viewer_can_read_only(self) -> None:
        assert can_perform("viewer", "read_list")
        assert can_perform("viewer", "list_items")

    def test_viewer_cannot_write(self) -> None:
        assert not can_perform("viewer", "create_item")
        assert not can_perform("viewer", "update_item")
        assert not can_perform("viewer", "delete_item")
        assert not can_perform("viewer", "rename_list")
        assert not can_perform("viewer", "delete_list")

    def test_unknown_action_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown action"):
            can_perform("owner", "fly_to_moon")
