from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import AppError
from app.models.reservation import Reservation, ReservationStatus
from app.models.resource import Resource
from app.schemas.reservation import (
    AvailabilityRead,
    AvailabilityWindow,
    AvailabilityWindowsRead,
)
from app.schemas.resource import ResourceCreate, ResourcePage, ResourceRead, ResourceUpdate
from app.services.reservation_service import (
    ensure_resource_is_active,
    find_available_windows,
    find_conflicts,
    get_reservation_or_error,
    get_resource_or_error,
    is_within_opening_hours,
    opening_windows,
    validate_availability_search_range,
    validate_time_range,
)

router = APIRouter(prefix="/resources", tags=["resources"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ResourceRead, status_code=status.HTTP_201_CREATED)
async def create_resource(payload: ResourceCreate, db: DbSession) -> Resource:
    resource = Resource(**payload.model_dump())
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


@router.get("", response_model=ResourcePage)
async def list_resources(
    db: DbSession,
    resource_type: str | None = None,
    is_active: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ResourcePage:
    filters = []
    if resource_type is not None:
        filters.append(Resource.resource_type == resource_type)
    if is_active is not None:
        filters.append(Resource.is_active == is_active)

    total = db.scalar(select(func.count(Resource.id)).where(*filters)) or 0
    query = (
        select(Resource)
        .where(*filters)
        .order_by(Resource.id)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(db.scalars(query))
    return ResourcePage(items=items, page=page, limit=limit, total=total)


@router.get("/available", response_model=ResourcePage)
async def list_available_resources(
    start_at: Annotated[datetime, Query()],
    end_at: Annotated[datetime, Query()],
    db: DbSession,
    resource_type: str | None = None,
    min_capacity: Annotated[int | None, Query(gt=0)] = None,
    exclude_reservation_id: Annotated[int | None, Query(gt=0)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ResourcePage:
    start_at, end_at = validate_time_range(start_at, end_at)
    if exclude_reservation_id is not None:
        get_reservation_or_error(db, exclude_reservation_id)

    conflict_filters = [
        Reservation.resource_id == Resource.id,
        Reservation.status != ReservationStatus.CANCELLED,
        Reservation.start_at < end_at,
        Reservation.end_at > start_at,
    ]
    if exclude_reservation_id is not None:
        conflict_filters.append(Reservation.id != exclude_reservation_id)
    has_conflict = (
        select(Reservation.id)
        .where(*conflict_filters)
        .exists()
    )
    filters = [Resource.is_active.is_(True), ~has_conflict]
    if resource_type is not None:
        filters.append(Resource.resource_type == resource_type)
    if min_capacity is not None:
        filters.append(Resource.capacity >= min_capacity)

    candidates = list(
        db.scalars(select(Resource).where(*filters).order_by(Resource.id))
    )
    available_resources = [
        resource
        for resource in candidates
        if is_within_opening_hours(resource, start_at, end_at)
    ]
    total = len(available_resources)
    items = available_resources[(page - 1) * limit : page * limit]
    return ResourcePage(items=items, page=page, limit=limit, total=total)


@router.get("/{resource_id}/available-windows", response_model=AvailabilityWindowsRead)
async def list_available_windows(
    resource_id: int,
    start_at: Annotated[datetime, Query()],
    end_at: Annotated[datetime, Query()],
    db: DbSession,
    minimum_duration_minutes: Annotated[int, Query(ge=30, le=480)] = 30,
    exclude_reservation_id: Annotated[int | None, Query(gt=0)] = None,
) -> AvailabilityWindowsRead:
    resource = get_resource_or_error(db, resource_id)
    ensure_resource_is_active(resource)
    if exclude_reservation_id is not None:
        get_reservation_or_error(db, exclude_reservation_id)
    start_at, end_at = validate_availability_search_range(start_at, end_at)
    windows = [
        available_window
        for opening_start, opening_end in opening_windows(resource, start_at, end_at)
        for available_window in find_available_windows(
            db,
            resource_id,
            opening_start,
            opening_end,
            minimum_duration=timedelta(minutes=minimum_duration_minutes),
            exclude_reservation_id=exclude_reservation_id,
        )
    ]
    return AvailabilityWindowsRead(
        resource_id=resource_id,
        start_at=start_at,
        end_at=end_at,
        minimum_duration_minutes=minimum_duration_minutes,
        windows=[
            AvailabilityWindow(start_at=window_start, end_at=window_end)
            for window_start, window_end in windows
        ],
    )


@router.get("/{resource_id}/availability", response_model=AvailabilityRead)
async def check_availability(
    resource_id: int,
    start_at: Annotated[str, Query()],
    end_at: Annotated[str, Query()],
    db: DbSession,
    exclude_reservation_id: Annotated[int | None, Query(gt=0)] = None,
) -> AvailabilityRead:
    try:
        parsed_start = datetime.fromisoformat(start_at)
        parsed_end = datetime.fromisoformat(end_at)
    except ValueError as exc:
        raise AppError(422, "INVALID_DATE_FORMAT", "Las fechas deben usar formato ISO 8601.") from exc

    resource = get_resource_or_error(db, resource_id)
    ensure_resource_is_active(resource)
    if exclude_reservation_id is not None:
        get_reservation_or_error(db, exclude_reservation_id)
    parsed_start, parsed_end = validate_time_range(parsed_start, parsed_end)
    conflicts = find_conflicts(
        db,
        resource_id,
        parsed_start,
        parsed_end,
        exclude_reservation_id=exclude_reservation_id,
    )
    return AvailabilityRead(
        resource_id=resource_id,
        available=(
            is_within_opening_hours(resource, parsed_start, parsed_end)
            and not conflicts
        ),
        conflicting_reservations=conflicts,
    )


@router.get("/{resource_id}", response_model=ResourceRead)
async def get_resource(resource_id: int, db: DbSession) -> Resource:
    return get_resource_or_error(db, resource_id)


@router.patch("/{resource_id}", response_model=ResourceRead)
async def update_resource(
    resource_id: int, payload: ResourceUpdate, db: DbSession
) -> Resource:
    resource = get_resource_or_error(db, resource_id)
    changes = payload.model_dump(exclude_unset=True)
    opening_time = changes.get("opening_time", resource.opening_time)
    closing_time = changes.get("closing_time", resource.closing_time)
    if (opening_time is None) != (closing_time is None):
        raise AppError(
            422,
            "INVALID_OPENING_HOURS",
            "La hora de apertura y cierre deben configurarse juntas.",
        )
    if (
        opening_time is not None
        and closing_time is not None
        and opening_time >= closing_time
    ):
        raise AppError(
            422,
            "INVALID_OPENING_HOURS",
            "La hora de cierre debe ser posterior a la de apertura.",
        )

    for field, value in changes.items():
        setattr(resource, field, value)
    db.commit()
    db.refresh(resource)
    return resource


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(resource_id: int, db: DbSession) -> Response:
    resource = get_resource_or_error(db, resource_id)
    has_reservations = db.scalar(
        select(Reservation.id).where(Reservation.resource_id == resource_id).limit(1)
    )
    if has_reservations is not None:
        raise AppError(
            409,
            "RESOURCE_DELETE_NOT_ALLOWED",
            "No se puede eliminar un recurso que tiene reservas asociadas.",
        )
    db.delete(resource)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
