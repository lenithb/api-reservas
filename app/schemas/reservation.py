from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.reservation import ReservationStatus
from app.schemas.common import ORMModel, Page


def require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value


class ReservationCreate(BaseModel):
    resource_id: int
    customer_id: int
    start_at: datetime
    end_at: datetime
    status: ReservationStatus = ReservationStatus.PENDING
    notes: str | None = None

    _validate_start_at = field_validator("start_at")(require_timezone)
    _validate_end_at = field_validator("end_at")(require_timezone)


class ReservationUpdate(BaseModel):
    resource_id: int | None = None
    customer_id: int | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: ReservationStatus | None = None
    notes: str | None = None

    @field_validator("resource_id", "customer_id", "start_at", "end_at", "status")
    @classmethod
    def required_fields_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value

    @field_validator("start_at", "end_at")
    @classmethod
    def datetimes_need_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            return require_timezone(value)
        return value


class ReservationRead(ORMModel):
    id: int
    resource_id: int
    customer_id: int
    start_at: datetime
    end_at: datetime
    status: ReservationStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None


class ReservationPage(Page[ReservationRead]):
    pass


class ConflictingReservation(ORMModel):
    id: int
    start_at: datetime
    end_at: datetime


class AvailabilityRead(BaseModel):
    resource_id: int
    available: bool
    conflicting_reservations: list[ConflictingReservation]
