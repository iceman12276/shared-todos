"""OQ-1 stranger-404 full matrix integration tests.

Verifies the load-bearing authorization invariant from PRD-3 / CLAUDE.md:
a stranger must receive 404 on EVERY verb against EVERY list/item/share
endpoint — never 403, never a leak of resource existence.

The parametrized grid below makes every (resource × verb) cell literal and
enumerable; a future regression in any single cell will show up as a named
failure in the matrix rather than a silent gap.

Additional tests:
- Multi-role scenario: editor can do item CRUD, cannot manage list/shares
- Anti-enumeration: 404 body must be byte-identical to nonexistent-list 404
- Cascade: deleting a list removes its items and shares
- Revocation: revoked editor loses access immediately (OQ-1 enforcement)
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.item import Item
from app.models.list_ import List
from app.models.share import Share
from tests.integration.helpers import register_user

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

BASE = "http://test"
GHOST_LIST_ID = "00000000-0000-0000-0000-000000000099"


# ── Fixtures ─────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient, email: str, password: str) -> None:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    client.headers["X-CSRF-Token"] = r.cookies.get("csrf_token") or ""


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession) -> tuple[User, User, User, List, Item]:
    """Seed owner, editor, stranger + list + item.

    Returns (owner, editor, stranger, lst, item).
    """
    owner = await register_user(db_session, "oq1_owner@example.com", "Owner", "Pass1234!")
    editor = await register_user(db_session, "oq1_editor@example.com", "Editor", "Pass1234!")
    stranger = await register_user(db_session, "oq1_stranger@example.com", "Stranger", "Pass1234!")

    lst = List(owner_id=owner.id, name="OQ1 List")
    db_session.add(lst)
    await db_session.commit()
    await db_session.refresh(lst)

    db_session.add(Share(list_id=lst.id, user_id=editor.id, role="editor"))
    item = Item(list_id=lst.id, content="Do something", order=0)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    return owner, editor, stranger, lst, item


# ── Stranger 404 parametrized matrix ─────────────────────────────────────────
#
# Grid: stranger × {list, item, share} × {POST, GET, PATCH, DELETE}
# Every cell must return 404 — never 403, never 200, never any information leak.
#
# Columns: (http_method, url_key, json_body_or_None, human_readable_cell_id)
#
# url_key values are resolved at runtime via the `seeded` fixture so that
# real list/item/share IDs are used in every cell.

_STRANGER_MATRIX: list[tuple[str, str, dict[str, Any] | None, str]] = [
    # ── list resource (GET/PATCH/DELETE /{list_id}) ────────────────────────
    # No POST /{list_id} exists — POST /lists creates an owned list (not gated by OQ-1).
    ("GET", "list", None, "list×GET"),
    ("PATCH", "list", {"name": "X"}, "list×PATCH"),
    ("DELETE", "list", None, "list×DELETE"),
    # ── item resource (POST/GET /items, PATCH/DELETE /items/{id}) ─────────
    ("POST", "items", {"content": "x", "order": 0}, "items×POST"),
    ("GET", "items", None, "items×GET"),
    ("PATCH", "item", {"content": "x"}, "item×PATCH"),
    ("DELETE", "item", None, "item×DELETE"),
    # ── share resource (POST/GET /shares, PATCH/DELETE /shares/{user_id}) ─
    ("POST", "shares", {"user_id": str(uuid.uuid4()), "role": "viewer"}, "shares×POST"),
    ("GET", "shares", None, "shares×GET"),
    ("PATCH", "share", {"role": "editor"}, "share×PATCH"),
    ("DELETE", "share", None, "share×DELETE"),
]


def _resolve_url(key: str, lst: List, item: Item) -> str:
    """Map a url_key to the actual endpoint path."""
    urls = {
        "list": f"/api/v1/lists/{lst.id}",
        "items": f"/api/v1/lists/{lst.id}/items",
        "item": f"/api/v1/lists/{lst.id}/items/{item.id}",
        "shares": f"/api/v1/lists/{lst.id}/shares",
        # any UUID is fine for share/{id} — authz fires before the record lookup
        "share": f"/api/v1/lists/{lst.id}/shares/{item.id}",
    }
    return urls[key]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "method,url_key,body,cell_id",
    _STRANGER_MATRIX,
    ids=[cell[3] for cell in _STRANGER_MATRIX],
)
async def test_stranger_404_matrix(
    seeded: tuple[User, User, User, List, Item],
    method: str,
    url_key: str,
    body: dict[str, Any] | None,
    cell_id: str,
) -> None:
    """Every (resource × verb) cell returns 404 for a stranger — never 403."""
    _, _, stranger, lst, item = seeded
    url = _resolve_url(url_key, lst, item)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "oq1_stranger@example.com", "Pass1234!")
        r = await c.request(method, url, json=body)

    assert r.status_code == 404, (
        f"cell {cell_id}: expected 404, got {r.status_code}. "
        "Stranger must never learn whether a resource exists."
    )
    assert r.status_code != 403, f"cell {cell_id}: 403 leaks resource existence (OQ-1 violation)"


# ── Anti-enumeration: real vs. nonexistent list → identical 404 body ─────────


@pytest.mark.anyio
async def test_anti_enum_list_404_body_identical(
    seeded: tuple[User, User, User, List, Item],
) -> None:
    """Stranger 404 body on a real list must be byte-identical to a ghost list 404.

    An attacker comparing response bodies must see zero signal difference between
    'exists but you can't see it' and 'doesn't exist at all'.
    """
    _, _, _, lst, _ = seeded

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "oq1_stranger@example.com", "Pass1234!")
        r_real = await c.get(f"/api/v1/lists/{lst.id}")
        r_ghost = await c.get(f"/api/v1/lists/{GHOST_LIST_ID}")

    assert r_real.status_code == 404
    assert r_ghost.status_code == 404
    assert r_real.content == r_ghost.content, (
        "404 body for a stranger-visible real list differs from nonexistent-list 404 "
        "— this leaks resource existence (OQ-1 anti-enumeration violation). "
        "Byte comparison (not JSON equality) catches future middleware fields "
        "like request_id/trace_id that would reintroduce an enumeration oracle."
    )


# ── Multi-role scenario: editor can do item CRUD, cannot manage list/shares ───


@pytest.mark.anyio
async def test_editor_can_create_item(
    seeded: tuple[User, User, User, List, Item],
) -> None:
    _, _, _, lst, _ = seeded

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "oq1_editor@example.com", "Pass1234!")
        r = await c.post(
            f"/api/v1/lists/{lst.id}/items",
            json={"content": "Editor item", "order": 1},
        )

    assert r.status_code == 201
    assert r.json()["content"] == "Editor item"


@pytest.mark.anyio
async def test_editor_can_update_item(
    seeded: tuple[User, User, User, List, Item],
) -> None:
    _, _, _, lst, item = seeded

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "oq1_editor@example.com", "Pass1234!")
        r = await c.patch(f"/api/v1/lists/{lst.id}/items/{item.id}", json={"completed": True})

    assert r.status_code == 200
    assert r.json()["completed"] is True


@pytest.mark.anyio
async def test_editor_can_delete_item(
    seeded: tuple[User, User, User, List, Item],
) -> None:
    _, _, _, lst, item = seeded

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "oq1_editor@example.com", "Pass1234!")
        r = await c.delete(f"/api/v1/lists/{lst.id}/items/{item.id}")

    assert r.status_code == 204


@pytest.mark.anyio
async def test_editor_cannot_rename_list(
    seeded: tuple[User, User, User, List, Item],
) -> None:
    _, _, _, lst, _ = seeded

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "oq1_editor@example.com", "Pass1234!")
        r = await c.patch(f"/api/v1/lists/{lst.id}", json={"name": "Hacked"})

    assert r.status_code == 404


@pytest.mark.anyio
async def test_editor_cannot_delete_list(
    seeded: tuple[User, User, User, List, Item],
) -> None:
    _, _, _, lst, _ = seeded

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "oq1_editor@example.com", "Pass1234!")
        r = await c.delete(f"/api/v1/lists/{lst.id}")

    assert r.status_code == 404


@pytest.mark.anyio
async def test_editor_cannot_view_shares(
    seeded: tuple[User, User, User, List, Item],
) -> None:
    _, _, _, lst, _ = seeded

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "oq1_editor@example.com", "Pass1234!")
        r = await c.get(f"/api/v1/lists/{lst.id}/shares")

    assert r.status_code == 404


@pytest.mark.anyio
async def test_editor_cannot_share_list(
    seeded: tuple[User, User, User, List, Item],
) -> None:
    _, _, stranger, lst, _ = seeded

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "oq1_editor@example.com", "Pass1234!")
        r = await c.post(
            f"/api/v1/lists/{lst.id}/shares",
            json={"user_id": str(stranger.id), "role": "viewer"},
        )

    assert r.status_code == 404


# ── Cascade: deleting a list removes items and shares ────────────────────────


@pytest.mark.anyio
async def test_delete_list_cascades_items_and_shares(
    seeded: tuple[User, User, User, List, Item],
    db_session: AsyncSession,
) -> None:
    _, editor, _, lst, item = seeded
    list_id = lst.id
    item_id = item.id
    editor_id = editor.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "oq1_owner@example.com", "Pass1234!")
        r_delete = await c.delete(f"/api/v1/lists/{lst.id}")

    assert r_delete.status_code == 204

    # Expire identity-map cache so the session re-fetches from DB
    db_session.expire_all()
    assert await db_session.get(List, list_id) is None
    assert await db_session.get(Item, item_id) is None
    # Share row must also be gone — ondelete="CASCADE" on shares.list_id FK
    share_result = await db_session.execute(
        sa.select(Share).where(Share.list_id == list_id, Share.user_id == editor_id)
    )
    assert share_result.scalar_one_or_none() is None, (
        "Share row survived list deletion — ondelete='CASCADE' on shares.list_id not working"
    )


# ── Revocation: revoked editor loses access immediately ──────────────────────


@pytest.mark.anyio
async def test_revoked_editor_loses_access_immediately(
    seeded: tuple[User, User, User, List, Item],
) -> None:
    owner, editor, _, lst, _ = seeded

    # Verify editor has access before revocation
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c_owner:
        await _login(c_owner, "oq1_owner@example.com", "Pass1234!")
        r_before = await c_owner.get(f"/api/v1/lists/{lst.id}/items")
        assert r_before.status_code == 200

        r_revoke = await c_owner.delete(f"/api/v1/lists/{lst.id}/shares/{editor.id}")
        assert r_revoke.status_code == 204

    # Editor's subsequent request must be 404 — OQ-1 is enforced immediately
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c_editor:
        await _login(c_editor, "oq1_editor@example.com", "Pass1234!")
        r_after = await c_editor.get(f"/api/v1/lists/{lst.id}/items")

    assert r_after.status_code == 404
