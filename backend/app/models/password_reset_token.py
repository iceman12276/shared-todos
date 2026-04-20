from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
