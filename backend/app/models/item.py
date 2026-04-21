from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    list_id: Mapped[UUID] = mapped_column(sa.ForeignKey("lists.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(sa.Text)
    completed: Mapped[bool] = mapped_column(sa.Boolean, default=False, server_default="false")
    order: Mapped[int] = mapped_column(sa.Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=sa.func.now(), onupdate=sa.func.now()
    )
