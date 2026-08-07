from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.schemas.common import ORMModel, Page

RequiredName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
ResourceType = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]


class ResourceCreate(BaseModel):
    name: RequiredName
    description: str | None = None
    resource_type: ResourceType
    capacity: int = Field(gt=0)
    is_active: bool = True


class ResourceUpdate(BaseModel):
    name: RequiredName | None = None
    description: str | None = None
    resource_type: ResourceType | None = None
    capacity: int | None = Field(default=None, gt=0)
    is_active: bool | None = None

    @field_validator("name", "resource_type", "capacity", "is_active")
    @classmethod
    def required_fields_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class ResourceRead(ORMModel):
    id: int
    name: str
    description: str | None
    resource_type: str
    capacity: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ResourcePage(Page[ResourceRead]):
    pass
