from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, StringConstraints, field_validator

from app.schemas.common import ORMModel, Page

FullUserName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)
]
UserRoleName = Literal["admin", "user"]
PlainPassword = Annotated[
    str, StringConstraints(min_length=8, max_length=72)
]


class UserCreate(BaseModel):
    full_name: FullUserName
    email: EmailStr
    password: PlainPassword
    role: UserRoleName = "user"


class UserUpdate(BaseModel):
    full_name: FullUserName | None = None
    email: EmailStr | None = None
    password: PlainPassword | None = None
    role: UserRoleName | None = None
    is_active: bool | None = None

    @field_validator("full_name", "email")
    @classmethod
    def required_fields_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class UserRead(ORMModel):
    id: int
    full_name: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserPage(Page[UserRead]):
    pass


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
