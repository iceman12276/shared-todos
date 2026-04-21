from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(sa.String(254), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(sa.String(128))
    password_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    google_sub: Mapped[str | None] = mapped_column(sa.String(256), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=sa.func.now(), onupdate=sa.func.now()
    )

    __table_args__ = (
        sa.CheckConstraint(
            "password_hash IS NOT NULL OR google_sub IS NOT NULL",
            name="ck_users_has_auth_method",
        ),
    )
