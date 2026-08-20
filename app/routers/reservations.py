from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import AppError
from app.models.reservation import Reservation, ReservationStatus
from app.schemas.reservation import (
    ReservationCreate,
    ReservationPage,
    ReservationRead,
    ReservationUpdate,
    RecurringReservationCreate,
)
from app.services.reservation_service import (
    cancel_reservation,
    create_reservation,
    create_recurring_reservations,
    get_reservation_or_error,
    update_reservation,
)

router = APIRouter(prefix="/reservations", tags=["reservations"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ReservationRead, status_code=status.HTTP_201_CREATED)
async def create(payload: ReservationCreate, db: DbSession) -> Reservation:
    return create_reservation(db, payload)


@router.post(
    "/recurring",
    response_model=list[ReservationRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_recurring(
    payload: RecurringReservationCreate, db: DbSession
) -> list[Reservation]:
    return create_recurring_reservations(db, payload)


@router.get("", response_model=ReservationPage)
async def list_reservations(
    db: DbSession,
    resource_id: int | None = None,
    customer_id: int | None = None,
    reservation_status: Annotated[
        ReservationStatus | None, Query(alias="status")
    ] = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ReservationPage:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise AppError(
            422,
            "INVALID_FILTER_DATE_RANGE",
            "La fecha inicial del filtro no puede ser posterior a la fecha final.",
        )

    filters = []
    if resource_id is not None:
        filters.append(Reservation.resource_id == resource_id)
    if customer_id is not None:
        filters.append(Reservation.customer_id == customer_id)
    if reservation_status is not None:
        filters.append(Reservation.status == reservation_status)
    if start_date is not None:
        start_boundary = datetime.combine(start_date, time.min, timezone.utc)
        filters.append(Reservation.end_at > start_boundary)
    if end_date is not None:
        end_boundary = datetime.combine(end_date + timedelta(days=1), time.min, timezone.utc)
        filters.append(Reservation.start_at < end_boundary)

    total = db.scalar(select(func.count(Reservation.id)).where(*filters)) or 0
    query = (
        select(Reservation)
        .where(*filters)
        .order_by(Reservation.start_at, Reservation.id)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(db.scalars(query))
    return ReservationPage(items=items, page=page, limit=limit, total=total)


@router.get("/{reservation_id}", response_model=ReservationRead)
async def get_reservation(reservation_id: int, db: DbSession) -> Reservation:
    return get_reservation_or_error(db, reservation_id)


@router.patch("/{reservation_id}", response_model=ReservationRead)
async def update(
    reservation_id: int, payload: ReservationUpdate, db: DbSession
) -> Reservation:
    reservation = get_reservation_or_error(db, reservation_id)
    return update_reservation(db, reservation, payload)


@router.post("/{reservation_id}/cancel", response_model=ReservationRead)
async def cancel(reservation_id: int, db: DbSession) -> Reservation:
    reservation = get_reservation_or_error(db, reservation_id)
    return cancel_reservation(db, reservation)
