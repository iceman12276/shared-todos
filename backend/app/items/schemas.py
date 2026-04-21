from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4096)
    order: int = Field(default=0)


class ItemUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=4096)
    completed: bool | None = None
    order: int | None = None


class ItemOut(BaseModel):
    id: UUID
    list_id: UUID
    content: str
    completed: bool
    order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
