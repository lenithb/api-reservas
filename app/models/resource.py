from datetime import datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, JSON, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.reservation import Reservation


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    opening_time: Mapped[time | None] = mapped_column(Time)
    closing_time: Mapped[time | None] = mapped_column(Time)
    closed_dates: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )

    reservations: Mapped[list["Reservation"]] = relationship(
        back_populates="resource", passive_deletes=True
    )
