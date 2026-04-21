from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ShareCreate(BaseModel):
    user_id: UUID
    role: str = Field(pattern=r"^(editor|viewer)$")


class ShareUpdate(BaseModel):
    role: str = Field(pattern=r"^(editor|viewer)$")


class ShareOut(BaseModel):
    list_id: UUID
    user_id: UUID
    role: str
    granted_at: datetime

    model_config = {"from_attributes": True}
