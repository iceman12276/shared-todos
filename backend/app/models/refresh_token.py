from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    family_id: Mapped[UUID] = mapped_column(sa.Uuid(), index=True)
    user_id: Mapped[UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    parent_token_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
    issued_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
