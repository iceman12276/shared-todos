from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Share(Base):
    __tablename__ = "shares"

    list_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("lists.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(sa.String(16))
    granted_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())

    __table_args__ = (
        sa.CheckConstraint("role IN ('editor', 'viewer')", name="role_valid"),
        # Uniqueness is already enforced by the composite PK (list_id, user_id).
        # No separate UniqueConstraint needed — it would create a redundant index.
    )
