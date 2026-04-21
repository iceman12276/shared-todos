"""Anti-enum: register response body shape must be identical for new vs existing email.

PR #2 QA finding: the duplicate-email branch returned {'user', 'message'} while
the new-email branch returned {'user'} only. A body-parsing caller could
distinguish email existence from the key set alone.

Fixed by returning {'user': None, 'message': <generic>} on both paths.
"""

import pytest
from httpx import ASGITransport, AsyncClient

BASE = "http://test"


@pytest.mark.asyncio
async def test_register_body_shape_identical_for_new_vs_existing_email() -> None:
    """Register response body keys must be identical for new and existing emails.

    Both paths must return {'user': ..., 'message': ...} so body-parsing callers
    cannot distinguish existing from new emails.
    """
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        # Register a known user
        r_first = await c.post(
            "/api/v1/auth/register",
            json={"email": "bodyshape_test@example.com", "password": "correcthorsebattery1"},
        )
        assert r_first.status_code == 201, f"First register failed: {r_first.status_code}"

        # Duplicate email path
        r_dup = await c.post(
            "/api/v1/auth/register",
            json={"email": "bodyshape_test@example.com", "password": "differentpassword12"},
        )

        # Brand new email path
        r_new = await c.post(
            "/api/v1/auth/register",
            json={"email": "brand_new_bodyshape@example.com", "password": "correcthorsebattery1"},
        )

    assert r_dup.status_code == 201, "Duplicate register must return 201 (anti-enum)"
    assert r_new.status_code == 201, "New register must return 201"

    dup_keys = set(r_dup.json().keys())
    new_keys = set(r_new.json().keys())

    assert dup_keys == new_keys, (
        f"Body shape leaks email existence. "
        f"Duplicate-email keys: {dup_keys}, "
        f"New-email keys: {new_keys}."
    )

    # Both must have 'user' and 'message'
    assert "user" in dup_keys
    assert "message" in dup_keys
