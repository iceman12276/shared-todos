"""Authorization permission matrix for list/item/share actions.

Roles: owner > editor > viewer. Strangers (no role) get 404, not 403.
This module contains pure logic — no DB, no FastAPI. Dependency wiring
lives in app.authz.dependencies.
"""

from typing import Literal

Role = Literal["owner", "editor", "viewer"]

# Actions that each role is permitted to perform.
_ALLOWED: dict[str, frozenset[str]] = {
    "owner": frozenset(
        [
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
    ),
    "editor": frozenset(
        [
            "read_list",
            "list_items",
            "create_item",
            "update_item",
            "delete_item",
        ]
    ),
    "viewer": frozenset(
        [
            "read_list",
            "list_items",
        ]
    ),
}

_ALL_ACTIONS = frozenset().union(*_ALLOWED.values())


def effective_role(*, is_owner: bool, share_role: str | None) -> Role | None:
    """Resolve the caller's effective role for a list.

    Returns None when the caller has no access (stranger → caller receives 404).
    Raises ValueError for any share_role value that is neither None, 'editor',
    nor 'viewer' — matching can_perform's raise-on-unknown-input contract.
    An unknown share_role indicates DB data drift (schema change without migration,
    or a direct DB edit). It is not a user-facing error; the caller surfaces it
    as 500 via FastAPI's default exception handler.
    """
    if is_owner:
        return "owner"
    if share_role == "editor":
        return "editor"
    if share_role == "viewer":
        return "viewer"
    if share_role is not None:
        raise ValueError(f"unknown share_role: {share_role!r}")
    return None


def can_perform(role: str, action: str) -> bool:
    """Return True if *role* may perform *action*.

    Raises ValueError for unknown actions to surface mis-wired call sites early.
    """
    if action not in _ALL_ACTIONS:
        raise ValueError(f"unknown action: {action!r}")
    allowed = _ALLOWED.get(role, frozenset())
    return action in allowed
