from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import AppError
from app.models.reservation import Reservation
from app.models.resource import Resource
from app.schemas.reservation import AvailabilityRead
from app.schemas.resource import ResourceCreate, ResourceRead, ResourceUpdate
from app.services.reservation_service import (
    ensure_resource_is_active,
    find_conflicts,
    get_resource_or_error,
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


@router.get("", response_model=list[ResourceRead])
async def list_resources(
    db: DbSession,
    resource_type: str | None = None,
    is_active: bool | None = None,
) -> list[Resource]:
    query = select(Resource)
    if resource_type is not None:
        query = query.where(Resource.resource_type == resource_type)
    if is_active is not None:
        query = query.where(Resource.is_active == is_active)
    return list(db.scalars(query.order_by(Resource.id)))


@router.get("/{resource_id}/availability", response_model=AvailabilityRead)
async def check_availability(
    resource_id: int,
    start_at: Annotated[str, Query()],
    end_at: Annotated[str, Query()],
    db: DbSession,
) -> AvailabilityRead:
    from datetime import datetime

    try:
        parsed_start = datetime.fromisoformat(start_at)
        parsed_end = datetime.fromisoformat(end_at)
    except ValueError as exc:
        raise AppError(422, "INVALID_DATE_FORMAT", "Las fechas deben usar formato ISO 8601.") from exc

    resource = get_resource_or_error(db, resource_id)
    ensure_resource_is_active(resource)
    parsed_start, parsed_end = validate_time_range(parsed_start, parsed_end)
    conflicts = find_conflicts(db, resource_id, parsed_start, parsed_end)
    return AvailabilityRead(
        resource_id=resource_id,
        available=not conflicts,
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
    for field, value in payload.model_dump(exclude_unset=True).items():
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
