"""Integration tests for share CRUD endpoints.

Covers PRD-3 matrix cells for share management (owner-only operations):
- POST /api/v1/lists/{id}/shares — create share (owner ALLOW; editor, viewer, stranger DENY)
- GET /api/v1/lists/{id}/shares — list collaborators (owner ALLOW; editor, viewer, stranger DENY)
- PATCH /api/v1/lists/{id}/shares/{user_id} — change role (owner ALLOW; others DENY)
- DELETE /api/v1/lists/{id}/shares/{user_id} — revoke share (owner ALLOW; others DENY)

Edge cases:
- Self-share rejected (400)
- Duplicate share rejected (409)
- Share with non-existent user returns 404 (OQ-1 anti-enum)
- Revoking non-existent share returns 404
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


async def _login(client: AsyncClient, email: str, password: str) -> None:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    client.headers["X-CSRF-Token"] = r.cookies.get("csrf_token") or ""


async def _seed(db: AsyncSession, owner_email: str = "owner@example.com") -> tuple[User, List]:
    """Seed owner + list, return (owner, lst)."""
    owner = await register_user(db, owner_email, "Owner", "Pass1234!")
    lst = List(owner_id=owner.id, name="List")
    db.add(lst)
    await db.commit()
    await db.refresh(lst)
    return owner, lst


def _shares_url(list_id: object) -> str:
    return f"/api/v1/lists/{list_id}/shares"


def _share_url(list_id: object, user_id: object) -> str:
    return f"/api/v1/lists/{list_id}/shares/{user_id}"


# ── POST /api/v1/lists/{id}/shares ──────────────────────────────────────────


@pytest.mark.anyio
async def test_create_share_owner(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session)
    target = await register_user(db_session, "target@example.com", "T", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner@example.com", "Pass1234!")
        r = await c.post(_shares_url(lst.id), json={"user_id": str(target.id), "role": "viewer"})

    assert r.status_code == 201
    data = r.json()
    assert data["role"] == "viewer"
    assert data["user_id"] == str(target.id)


@pytest.mark.anyio
async def test_create_share_editor_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner2@example.com")
    editor = await register_user(db_session, "editor2@example.com", "Ed", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=editor.id, role="editor"))
    target = await register_user(db_session, "target2@example.com", "T2", "Pass1234!")
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "editor2@example.com", "Pass1234!")
        r = await c.post(_shares_url(lst.id), json={"user_id": str(target.id), "role": "viewer"})

    assert r.status_code == 404


@pytest.mark.anyio
async def test_create_share_viewer_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner3@example.com")
    viewer = await register_user(db_session, "viewer3@example.com", "Vi", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=viewer.id, role="viewer"))
    target = await register_user(db_session, "target3@example.com", "T3", "Pass1234!")
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "viewer3@example.com", "Pass1234!")
        r = await c.post(_shares_url(lst.id), json={"user_id": str(target.id), "role": "viewer"})

    assert r.status_code == 404


@pytest.mark.anyio
async def test_create_share_stranger_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner4@example.com")
    await register_user(db_session, "stranger4@example.com", "S", "Pass1234!")
    target = await register_user(db_session, "target4@example.com", "T4", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger4@example.com", "Pass1234!")
        r = await c.post(_shares_url(lst.id), json={"user_id": str(target.id), "role": "viewer"})

    assert r.status_code == 404


@pytest.mark.anyio
async def test_create_share_self_rejected(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner5@example.com")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner5@example.com", "Pass1234!")
        r = await c.post(_shares_url(lst.id), json={"user_id": str(owner.id), "role": "editor"})

    assert r.status_code == 400


@pytest.mark.anyio
async def test_create_share_nonexistent_user_404(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner6@example.com")
    fake_user_id = "00000000-0000-0000-0000-000000000000"

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner6@example.com", "Pass1234!")
        r = await c.post(_shares_url(lst.id), json={"user_id": fake_user_id, "role": "viewer"})

    assert r.status_code == 404


@pytest.mark.anyio
async def test_create_share_duplicate_rejected(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner7@example.com")
    target = await register_user(db_session, "target7@example.com", "T7", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=target.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner7@example.com", "Pass1234!")
        r = await c.post(_shares_url(lst.id), json={"user_id": str(target.id), "role": "editor"})

    assert r.status_code == 409


# ── GET /api/v1/lists/{id}/shares ────────────────────────────────────────────


@pytest.mark.anyio
async def test_list_shares_owner(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner8@example.com")
    collab = await register_user(db_session, "collab8@example.com", "C8", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=collab.id, role="editor"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner8@example.com", "Pass1234!")
        r = await c.get(_shares_url(lst.id))

    assert r.status_code == 200
    user_ids = [s["user_id"] for s in r.json()]
    assert str(collab.id) in user_ids


@pytest.mark.anyio
async def test_list_shares_editor_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner9@example.com")
    editor = await register_user(db_session, "editor9@example.com", "Ed9", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=editor.id, role="editor"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "editor9@example.com", "Pass1234!")
        r = await c.get(_shares_url(lst.id))

    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_shares_viewer_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner10@example.com")
    viewer = await register_user(db_session, "viewer10@example.com", "Vi10", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=viewer.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "viewer10@example.com", "Pass1234!")
        r = await c.get(_shares_url(lst.id))

    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_shares_stranger_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner11@example.com")
    await register_user(db_session, "stranger11@example.com", "S11", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger11@example.com", "Pass1234!")
        r = await c.get(_shares_url(lst.id))

    assert r.status_code == 404


# ── PATCH /api/v1/lists/{id}/shares/{user_id} ────────────────────────────────


@pytest.mark.anyio
async def test_change_role_owner(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner12@example.com")
    collab = await register_user(db_session, "collab12@example.com", "C12", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=collab.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner12@example.com", "Pass1234!")
        r = await c.patch(_share_url(lst.id, collab.id), json={"role": "editor"})

    assert r.status_code == 200
    assert r.json()["role"] == "editor"


@pytest.mark.anyio
async def test_change_role_editor_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner13@example.com")
    editor = await register_user(db_session, "editor13@example.com", "Ed13", "Pass1234!")
    collab = await register_user(db_session, "collab13@example.com", "C13", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=editor.id, role="editor"))
    db_session.add(Share(list_id=lst.id, user_id=collab.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "editor13@example.com", "Pass1234!")
        r = await c.patch(_share_url(lst.id, collab.id), json={"role": "editor"})

    assert r.status_code == 404


@pytest.mark.anyio
async def test_change_role_nonexistent_collaborator(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner14@example.com")
    ghost = await register_user(db_session, "ghost14@example.com", "G14", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner14@example.com", "Pass1234!")
        r = await c.patch(_share_url(lst.id, ghost.id), json={"role": "editor"})

    assert r.status_code == 404


# ── DELETE /api/v1/lists/{id}/shares/{user_id} ───────────────────────────────


@pytest.mark.anyio
async def test_revoke_share_owner(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner15@example.com")
    collab = await register_user(db_session, "collab15@example.com", "C15", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=collab.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner15@example.com", "Pass1234!")
        r = await c.delete(_share_url(lst.id, collab.id))

    assert r.status_code == 204


@pytest.mark.anyio
async def test_revoke_share_editor_denied(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner16@example.com")
    editor = await register_user(db_session, "editor16@example.com", "Ed16", "Pass1234!")
    collab = await register_user(db_session, "collab16@example.com", "C16", "Pass1234!")
    db_session.add(Share(list_id=lst.id, user_id=editor.id, role="editor"))
    db_session.add(Share(list_id=lst.id, user_id=collab.id, role="viewer"))
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "editor16@example.com", "Pass1234!")
        r = await c.delete(_share_url(lst.id, collab.id))

    assert r.status_code == 404


@pytest.mark.anyio
async def test_revoke_share_nonexistent(db_session: AsyncSession) -> None:
    owner, lst = await _seed(db_session, "owner17@example.com")
    ghost = await register_user(db_session, "ghost17@example.com", "G17", "Pass1234!")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner17@example.com", "Pass1234!")
        r = await c.delete(_share_url(lst.id, ghost.id))

    assert r.status_code == 404
