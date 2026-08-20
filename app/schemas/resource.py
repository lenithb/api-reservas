from datetime import date, datetime, time
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, ValidationInfo, field_validator

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
    opening_time: time | None = None
    closing_time: time | None = None
    closed_dates: list[date] = Field(default_factory=list)

    @field_validator("closing_time")
    @classmethod
    def closing_time_must_follow_opening_time(
        cls, value: time | None, info: ValidationInfo
    ) -> time | None:
        opening_time = info.data.get("opening_time")
        if (opening_time is None) != (value is None):
            raise ValueError("opening_time and closing_time must be provided together")
        if opening_time is not None and value is not None and opening_time >= value:
            raise ValueError("closing_time must be later than opening_time")
        return value


class ResourceUpdate(BaseModel):
    name: RequiredName | None = None
    description: str | None = None
    resource_type: ResourceType | None = None
    capacity: int | None = Field(default=None, gt=0)
    is_active: bool | None = None
    opening_time: time | None = None
    closing_time: time | None = None
    closed_dates: list[date] | None = None

    @field_validator("name", "resource_type", "capacity", "is_active", "closed_dates")
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
    opening_time: time | None
    closing_time: time | None
    closed_dates: list[date]
    created_at: datetime
    updated_at: datetime


class ResourcePage(Page[ResourceRead]):
    pass
