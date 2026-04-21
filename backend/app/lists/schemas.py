from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class ListUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class ListOut(BaseModel):
    id: UUID
    owner_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
