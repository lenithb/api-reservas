from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints, field_validator

from app.schemas.common import ORMModel, Page

FullName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)
]


class CustomerCreate(BaseModel):
    full_name: FullName
    email: EmailStr
    phone: str | None = None


class CustomerUpdate(BaseModel):
    full_name: FullName | None = None
    email: EmailStr | None = None
    phone: str | None = None

    @field_validator("full_name", "email")
    @classmethod
    def required_fields_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class CustomerRead(ORMModel):
    id: int
    full_name: str
    email: EmailStr
    phone: str | None
    created_at: datetime
    updated_at: datetime


class CustomerPage(Page[CustomerRead]):
    pass
