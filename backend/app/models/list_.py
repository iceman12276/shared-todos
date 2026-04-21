from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class List(Base):
    __tablename__ = "lists"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(sa.String(256))
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=sa.func.now(), onupdate=sa.func.now()
    )
