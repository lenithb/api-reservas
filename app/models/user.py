from datetime import datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime, utc_now

UserRole = Literal["admin", "user"]


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )

    if TYPE_CHECKING:
        # narrows the SQLAlchemy descriptor under type checking only
        role: UserRole
