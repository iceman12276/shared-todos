"""Integration tests for require_list_permission FastAPI dependency.

Covers:
- Owner can access their list (reads owner_id from lists table)
- Editor/viewer can access via shares table
- Stranger gets 404 (OQ-1: never 403, same body whether list exists or not)
- Non-existent list also gets 404 with identical body (anti-enum)
- 401 for unauthenticated requests
"""

from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.routing import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.authz.dependencies import ListPermission, require_list_permission
from app.main import app
from app.models.list_ import List
from app.models.share import Share
from app.models.user import User
from tests.integration.helpers import register_user

BASE = "http://test"

# Minimal probe endpoint so we can test the dependency before real list routes exist.
_probe_router = APIRouter()


@_probe_router.get("/test-authz/{list_id}")
async def _probe(
    perm: ListPermission = Depends(require_list_permission("read_list")),  # noqa: B008
) -> dict[str, str]:
    return {"role": perm.role}


app.include_router(_probe_router)


async def _create_list(db: AsyncSession, owner: User, name: str = "Test List") -> List:
    lst = List(owner_id=owner.id, name=name)
    db.add(lst)
    await db.commit()
    await db.refresh(lst)
    return lst


async def _create_share(db: AsyncSession, lst: List, user: User, role: str) -> Share:
    share = Share(list_id=lst.id, user_id=user.id, role=role)
    db.add(share)
    await db.commit()
    return share


async def _login(client: AsyncClient, email: str, password: str) -> None:
    await client.post("/api/v1/auth/login", json={"email": email, "password": password})


@pytest.mark.anyio
async def test_owner_gets_200(db_session: AsyncSession) -> None:
    owner = await register_user(db_session, "owner@example.com", "Owner", "Pass1234!")
    lst = await _create_list(db_session, owner)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "owner@example.com", "Pass1234!")
        r = await c.get(f"/test-authz/{lst.id}")

    assert r.status_code == 200
    assert r.json()["role"] == "owner"


@pytest.mark.anyio
async def test_editor_gets_200(db_session: AsyncSession) -> None:
    owner = await register_user(db_session, "owner2@example.com", "Owner2", "Pass1234!")
    editor = await register_user(db_session, "editor@example.com", "Editor", "Pass1234!")
    lst = await _create_list(db_session, owner)
    await _create_share(db_session, lst, editor, "editor")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "editor@example.com", "Pass1234!")
        r = await c.get(f"/test-authz/{lst.id}")

    assert r.status_code == 200
    assert r.json()["role"] == "editor"


@pytest.mark.anyio
async def test_viewer_gets_200(db_session: AsyncSession) -> None:
    owner = await register_user(db_session, "owner3@example.com", "Owner3", "Pass1234!")
    viewer = await register_user(db_session, "viewer@example.com", "Viewer", "Pass1234!")
    lst = await _create_list(db_session, owner)
    await _create_share(db_session, lst, viewer, "viewer")

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "viewer@example.com", "Pass1234!")
        r = await c.get(f"/test-authz/{lst.id}")

    assert r.status_code == 200
    assert r.json()["role"] == "viewer"


@pytest.mark.anyio
async def test_stranger_gets_404_oq1(db_session: AsyncSession) -> None:
    """OQ-1: stranger accessing a real list → 404, never 403."""
    owner = await register_user(db_session, "owner4@example.com", "Owner4", "Pass1234!")
    await register_user(db_session, "stranger@example.com", "Stranger", "Pass1234!")
    lst = await _create_list(db_session, owner)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger@example.com", "Pass1234!")
        r = await c.get(f"/test-authz/{lst.id}")

    assert r.status_code == 404
    assert r.status_code != 403


@pytest.mark.anyio
async def test_nonexistent_list_gets_404_same_body(db_session: AsyncSession) -> None:
    """Anti-enum: nonexistent list → same 404 body as stranger-on-real-list."""
    owner = await register_user(db_session, "owner5@example.com", "Owner5", "Pass1234!")
    await register_user(db_session, "stranger2@example.com", "Stranger2", "Pass1234!")
    lst = await _create_list(db_session, owner)

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        await _login(c, "stranger2@example.com", "Pass1234!")
        r_real = await c.get(f"/test-authz/{lst.id}")
        r_ghost = await c.get(f"/test-authz/{uuid4()}")

    assert r_real.status_code == 404
    assert r_ghost.status_code == 404
    assert r_real.json() == r_ghost.json()


@pytest.mark.anyio
async def test_unauthenticated_gets_401(db_session: AsyncSession) -> None:
    fake_id = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        r = await c.get(f"/test-authz/{fake_id}")
    assert r.status_code == 401
