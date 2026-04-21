"""Integration tests for item CRUD endpoints.

Covers PRD-3 matrix cells for item operations:
- POST /api/v1/lists/{id}/items — owner, editor ALLOW; viewer, stranger DENY
- GET /api/v1/lists/{id}/items — owner, editor, viewer ALLOW; stranger DENY
- PATCH /api/v1/lists/{id}/items/{item_id} — owner, editor ALLOW; viewer, stranger DENY
- DELETE /api/v1/lists/{id}/items/{item_id} — owner, editor ALLOW; viewer, stranger DENY
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.item import Item
from app.models.list_ import List
from app.models.share import Share
from app.models.user import User
from tests.integration.helpers import register_user

BASE = "http://test"


async def _login(client: AsyncClient, email: str, password: str) -> None:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    client.headers["X-CSRF-Token"] = r.cookies.get("csrf_token") or ""


async def _seed(
    db: AsyncSession, owner_email: str = "owner@example.com"
) -> tuple[User, List, Item]:
    """Seed owner + list + item, return (owner, lst, item)."""
    owner = await register_user(db, owner_email, "Owner", "Pass1234!")
    lst = List(owner_id=owner.id, name="List")
    db.add(lst)
    await db.commit()
    await db.refresh(lst)
    item = Item(list_id=lst.id, content="Do something", order=0)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return owner, lst, item


def _items_url(list_id: object) -> str:
    return f"/api/v1/lists/{list_id}/items"


def _item_url(list_id: object, item_id: object) -> str:
    return f"/api/v1/lists/{list_id}/items/{item_id}"


# ── POST /api/v1/lists/{id}/items ───────────────────────────────────────────


@pytest.mark.anyio
async def test_create_item_owner(db_session: AsyncSession) -> None:
    owner, lst, _ = await _seed(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner@example.com", "Pass1234!")
        r = await c.post(_items_url(lst.id), json={"content": "Buy milk", "order": 1})

    assert r.status_code == 201
    assert r.json()["content"] == "Buy milk"


@pytest.mark.anyio
async def test_create_item_editor(db_session: AsyncSession) -> None:
    owner, lst, _ = await _seed(db_session, "owner2@example.com")
    editor = await register_user(db_session, "editor@example.com", "Ed", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=editor.id, role="editor"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "editor@example.com", "Pass1234!")
        r = await c.post(_items_url(lst.id), json={"content": "Editor task", "order": 2})

    assert r.status_code == 201


@pytest.mark.anyio
async def test_create_item_viewer_denied(db_session: AsyncSession) -> None:
    owner, lst, _ = await _seed(db_session, "owner3@example.com")
    viewer = await register_user(db_session, "viewer@example.com", "Vi", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=viewer.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "viewer@example.com", "Pass1234!")
        r = await c.post(_items_url(lst.id), json={"content": "x", "order": 0})

    assert r.status_code == 404


@pytest.mark.anyio
async def test_create_item_stranger_denied(db_session: AsyncSession) -> None:
    owner, lst, _ = await _seed(db_session, "owner4@example.com")
    await register_user(db_session, "stranger@example.com", "S", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger@example.com", "Pass1234!")
        r = await c.post(_items_url(lst.id), json={"content": "x", "order": 0})

    assert r.status_code == 404


# ── GET /api/v1/lists/{id}/items ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_list_items_owner(db_session: AsyncSession) -> None:
    owner, lst, item = await _seed(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner@example.com", "Pass1234!")
        r = await c.get(_items_url(lst.id))

    assert r.status_code == 200
    ids = [i["id"] for i in r.json()]
    assert str(item.id) in ids


@pytest.mark.anyio
async def test_list_items_viewer(db_session: AsyncSession) -> None:
    owner, lst, item = await _seed(db_session, "owner5@example.com")
    viewer = await register_user(db_session, "viewer2@example.com", "Vi2", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=viewer.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "viewer2@example.com", "Pass1234!")
        r = await c.get(_items_url(lst.id))

    assert r.status_code == 200


@pytest.mark.anyio
async def test_list_items_stranger_denied(db_session: AsyncSession) -> None:
    owner, lst, _ = await _seed(db_session, "owner6@example.com")
    await register_user(db_session, "stranger2@example.com", "S2", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger2@example.com", "Pass1234!")
        r = await c.get(_items_url(lst.id))

    assert r.status_code == 404


# ── PATCH /api/v1/lists/{id}/items/{item_id} ─────────────────────────────────


@pytest.mark.anyio
async def test_update_item_owner(db_session: AsyncSession) -> None:
    owner, lst, item = await _seed(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner@example.com", "Pass1234!")
        r = await c.patch(_item_url(lst.id, item.id), json={"content": "Updated"})

    assert r.status_code == 200
    assert r.json()["content"] == "Updated"


@pytest.mark.anyio
async def test_update_item_editor(db_session: AsyncSession) -> None:
    owner, lst, item = await _seed(db_session, "owner7@example.com")
    editor = await register_user(db_session, "editor7@example.com", "Ed7", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=editor.id, role="editor"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "editor7@example.com", "Pass1234!")
        r = await c.patch(_item_url(lst.id, item.id), json={"completed": True})

    assert r.status_code == 200
    assert r.json()["completed"] is True


@pytest.mark.anyio
async def test_update_item_viewer_denied(db_session: AsyncSession) -> None:
    owner, lst, item = await _seed(db_session, "owner8@example.com")
    viewer = await register_user(db_session, "viewer8@example.com", "Vi8", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=viewer.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "viewer8@example.com", "Pass1234!")
        r = await c.patch(_item_url(lst.id, item.id), json={"content": "x"})

    assert r.status_code == 404


@pytest.mark.anyio
async def test_update_item_stranger_denied(db_session: AsyncSession) -> None:
    owner, lst, item = await _seed(db_session, "owner9@example.com")
    await register_user(db_session, "stranger9@example.com", "S9", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger9@example.com", "Pass1234!")
        r = await c.patch(_item_url(lst.id, item.id), json={"content": "x"})

    assert r.status_code == 404


# ── DELETE /api/v1/lists/{id}/items/{item_id} ────────────────────────────────


@pytest.mark.anyio
async def test_delete_item_owner(db_session: AsyncSession) -> None:
    owner, lst, item = await _seed(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner@example.com", "Pass1234!")
        r = await c.delete(_item_url(lst.id, item.id))

    assert r.status_code == 204


@pytest.mark.anyio
async def test_delete_item_editor(db_session: AsyncSession) -> None:
    owner, lst, item = await _seed(db_session, "owner10@example.com")
    editor = await register_user(db_session, "editor10@example.com", "Ed10", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=editor.id, role="editor"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "editor10@example.com", "Pass1234!")
        r = await c.delete(_item_url(lst.id, item.id))

    assert r.status_code == 204


@pytest.mark.anyio
async def test_delete_item_viewer_denied(db_session: AsyncSession) -> None:
    owner, lst, item = await _seed(db_session, "owner11@example.com")
    viewer = await register_user(db_session, "viewer11@example.com", "Vi11", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=viewer.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "viewer11@example.com", "Pass1234!")
        r = await c.delete(_item_url(lst.id, item.id))

    assert r.status_code == 404


@pytest.mark.anyio
async def test_delete_item_stranger_denied(db_session: AsyncSession) -> None:
    owner, lst, item = await _seed(db_session, "owner12@example.com")
    await register_user(db_session, "stranger12@example.com", "S12", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger12@example.com", "Pass1234!")
        r = await c.delete(_item_url(lst.id, item.id))

    assert r.status_code == 404


# ── Path parameter validation (UUID coercion) ────────────────────────────────


@pytest.mark.anyio
async def test_patch_item_bad_uuid_returns_422(db_session: AsyncSession) -> None:
    """PATCH with a non-UUID item_id segment must return 422, not 500."""
    owner, lst, _ = await _seed(db_session, "owner13@example.com")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner13@example.com", "Pass1234!")
        r = await c.patch(_item_url(lst.id, "not-a-uuid"), json={"content": "x"})

    assert r.status_code == 422


@pytest.mark.anyio
async def test_delete_item_bad_uuid_returns_422(db_session: AsyncSession) -> None:
    """DELETE with a non-UUID item_id segment must return 422, not 500."""
    owner, lst, _ = await _seed(db_session, "owner14@example.com")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner14@example.com", "Pass1234!")
        r = await c.delete(_item_url(lst.id, "not-a-uuid"))

    assert r.status_code == 422
