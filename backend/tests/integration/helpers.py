"""Shared helpers for integration tests.

These create DB rows directly to avoid HTTP round-trips when seeding test data.
All passwords are argon2-hashed the same way the real register endpoint does it.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password
from app.models.user import User


async def register_user(
    db: AsyncSession,
    email: str,
    display_name: str,
    password: str,
) -> User:
    """Insert a User with a hashed password directly into the DB."""
    user = User(
        email=email,
        display_name=display_name,
        password_hash=hash_password(password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
