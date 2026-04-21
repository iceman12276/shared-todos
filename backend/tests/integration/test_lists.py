"""Integration tests for list CRUD endpoints.

Covers every role × action cell from PRD-3 authorization matrix for list operations:
- POST /api/v1/lists — create (authenticated users only)
- GET /api/v1/lists — list owned + shared lists
- GET /api/v1/lists/{id} — read list metadata
- PATCH /api/v1/lists/{id} — rename (owner only)
- DELETE /api/v1/lists/{id} — delete (owner only)
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.list_ import List
from app.models.share import Share
from app.models.user import User
from tests.integration.helpers import register_user

BASE = "http://test"
LISTS_URL = "/api/v1/lists"


async def _login(client: AsyncClient, email: str, password: str) -> None:
    """Login and inject CSRF token into client headers for subsequent mutations."""
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    client.headers["X-CSRF-Token"] = r.cookies.get("csrf_token") or ""


async def _seed_list(db: AsyncSession, owner_email: str = "owner@example.com") -> tuple[User, List]:
    """Seed an owner user + list, return (owner, list)."""
    owner = await register_user(db, owner_email, "Owner", "Pass1234!")
    lst = List(owner_id=owner.id, name="My List")
    db.add(lst)
    await db.commit()
    await db.refresh(lst)
    return owner, lst


# ── POST /api/v1/lists ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_create_list_success(db_session: AsyncSession) -> None:
    await register_user(db_session, "creator@example.com", "Creator", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "creator@example.com", "Pass1234!")
        r = await c.post(LISTS_URL, json={"name": "Shopping"})

    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Shopping"
    assert "id" in data
    assert "owner_id" in data


@pytest.mark.anyio
async def test_create_list_unauthenticated(db_session: AsyncSession) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.post(LISTS_URL, json={"name": "x"})
    assert r.status_code == 401


@pytest.mark.anyio
async def test_create_list_empty_name_rejected(db_session: AsyncSession) -> None:
    await register_user(db_session, "u@example.com", "U", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "u@example.com", "Pass1234!")
        r = await c.post(LISTS_URL, json={"name": ""})

    assert r.status_code == 422


# ── GET /api/v1/lists ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_list_lists_shows_owned(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner@example.com", "Pass1234!")
        r = await c.get(LISTS_URL)

    assert r.status_code == 200
    ids = [item["id"] for item in r.json()]
    assert str(lst.id) in ids


@pytest.mark.anyio
async def test_list_lists_shows_shared(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session, "listowner@example.com")
    collab = await register_user(db_session, "collab@example.com", "Collab", "Pass1234!")
    share = Share(list_id=lst.id, user_id=collab.id, role="viewer")
    db_session.add(share)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "collab@example.com", "Pass1234!")
        r = await c.get(LISTS_URL)

    assert r.status_code == 200
    ids = [item["id"] for item in r.json()]
    assert str(lst.id) in ids


@pytest.mark.anyio
async def test_list_lists_excludes_strangers_lists(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session, "private@example.com")
    await register_user(db_session, "stranger@example.com", "Stranger", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger@example.com", "Pass1234!")
        r = await c.get(LISTS_URL)

    assert r.status_code == 200
    ids = [item["id"] for item in r.json()]
    assert str(lst.id) not in ids


# ── GET /api/v1/lists/{id} ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_list_owner(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner@example.com", "Pass1234!")
        r = await c.get(f"{LISTS_URL}/{lst.id}")

    assert r.status_code == 200
    assert r.json()["id"] == str(lst.id)


@pytest.mark.anyio
async def test_get_list_editor(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session, "listowner2@example.com")
    editor = await register_user(db_session, "editor2@example.com", "Ed", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=editor.id, role="editor"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "editor2@example.com", "Pass1234!")
        r = await c.get(f"{LISTS_URL}/{lst.id}")

    assert r.status_code == 200


@pytest.mark.anyio
async def test_get_list_viewer(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session, "listowner3@example.com")
    viewer = await register_user(db_session, "viewer2@example.com", "Vi", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=viewer.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "viewer2@example.com", "Pass1234!")
        r = await c.get(f"{LISTS_URL}/{lst.id}")

    assert r.status_code == 200


@pytest.mark.anyio
async def test_get_list_stranger_404(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session, "private2@example.com")
    await register_user(db_session, "stranger2@example.com", "S", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger2@example.com", "Pass1234!")
        r = await c.get(f"{LISTS_URL}/{lst.id}")

    assert r.status_code == 404
    assert r.status_code != 403


# ── PATCH /api/v1/lists/{id} ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_rename_list_owner(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner@example.com", "Pass1234!")
        r = await c.patch(f"{LISTS_URL}/{lst.id}", json={"name": "Renamed"})

    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"


@pytest.mark.anyio
async def test_rename_list_editor_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session, "owner6@example.com")
    editor = await register_user(db_session, "editor6@example.com", "Ed6", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=editor.id, role="editor"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "editor6@example.com", "Pass1234!")
        r = await c.patch(f"{LISTS_URL}/{lst.id}", json={"name": "Hacked"})

    assert r.status_code == 404


@pytest.mark.anyio
async def test_rename_list_viewer_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session, "owner7@example.com")
    viewer = await register_user(db_session, "viewer7@example.com", "Vi7", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=viewer.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "viewer7@example.com", "Pass1234!")
        r = await c.patch(f"{LISTS_URL}/{lst.id}", json={"name": "Hacked"})

    assert r.status_code == 404


@pytest.mark.anyio
async def test_rename_list_stranger_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session, "owner8@example.com")
    await register_user(db_session, "stranger8@example.com", "S8", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger8@example.com", "Pass1234!")
        r = await c.patch(f"{LISTS_URL}/{lst.id}", json={"name": "Hacked"})

    assert r.status_code == 404


# ── DELETE /api/v1/lists/{id} ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_delete_list_owner(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner@example.com", "Pass1234!")
        r = await c.delete(f"{LISTS_URL}/{lst.id}")

    assert r.status_code == 204


@pytest.mark.anyio
async def test_delete_list_editor_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session, "owner9@example.com")
    editor = await register_user(db_session, "editor9@example.com", "Ed9", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=editor.id, role="editor"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "editor9@example.com", "Pass1234!")
        r = await c.delete(f"{LISTS_URL}/{lst.id}")

    assert r.status_code == 404


@pytest.mark.anyio
async def test_delete_list_stranger_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed_list(db_session, "owner10@example.com")
    await register_user(db_session, "stranger10@example.com", "S10", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger10@example.com", "Pass1234!")
        r = await c.delete(f"{LISTS_URL}/{lst.id}")

    assert r.status_code == 404
