from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.database import utc_now
from app.exceptions import AppError
from app.models.customer import Customer
from app.models.reservation import Reservation, ReservationStatus
from app.models.resource import Resource
from app.schemas.reservation import ReservationCreate, ReservationUpdate

MINIMUM_DURATION = timedelta(minutes=30)
MAXIMUM_DURATION = timedelta(hours=8)


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppError(
            422,
            "INVALID_TIMEZONE",
            "Las fechas deben incluir una zona horaria.",
        )
    return value.astimezone(timezone.utc)


def validate_time_range(start_at: datetime, end_at: datetime) -> tuple[datetime, datetime]:
    start_at = normalize_datetime(start_at)
    end_at = normalize_datetime(end_at)

    if start_at >= end_at:
        raise AppError(
            422,
            "INVALID_DATE_RANGE",
            "La fecha de inicio debe ser anterior a la fecha de finalización.",
        )
    if start_at < utc_now():
        raise AppError(
            422,
            "RESERVATION_IN_PAST",
            "No se pueden crear o mover reservas al pasado.",
        )

    duration = end_at - start_at
    if duration < MINIMUM_DURATION:
        raise AppError(
            422,
            "RESERVATION_TOO_SHORT",
            "La duración mínima de una reserva es de 30 minutos.",
        )
    if duration > MAXIMUM_DURATION:
        raise AppError(
            422,
            "RESERVATION_TOO_LONG",
            "La duración máxima de una reserva es de 8 horas.",
        )
    return start_at, end_at


def get_resource_or_error(db: Session, resource_id: int) -> Resource:
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise AppError(404, "RESOURCE_NOT_FOUND", "El recurso solicitado no existe.")
    return resource


def get_customer_or_error(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise AppError(404, "CUSTOMER_NOT_FOUND", "El cliente solicitado no existe.")
    return customer


def get_reservation_or_error(db: Session, reservation_id: int) -> Reservation:
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise AppError(404, "RESERVATION_NOT_FOUND", "La reserva solicitada no existe.")
    return reservation


def ensure_resource_is_active(resource: Resource) -> None:
    if not resource.is_active:
        raise AppError(
            409,
            "RESOURCE_INACTIVE",
            "No se pueden registrar reservas sobre un recurso inactivo.",
        )


def conflict_query(
    resource_id: int,
    start_at: datetime,
    end_at: datetime,
    exclude_reservation_id: int | None = None,
) -> Select[tuple[Reservation]]:
    query = select(Reservation).where(
        Reservation.resource_id == resource_id,
        Reservation.status != ReservationStatus.CANCELLED,
        Reservation.start_at < end_at,
        Reservation.end_at > start_at,
    )
    if exclude_reservation_id is not None:
        query = query.where(Reservation.id != exclude_reservation_id)
    return query.order_by(Reservation.start_at)


def find_conflicts(
    db: Session,
    resource_id: int,
    start_at: datetime,
    end_at: datetime,
    exclude_reservation_id: int | None = None,
) -> list[Reservation]:
    return list(
        db.scalars(
            conflict_query(
                resource_id,
                start_at,
                end_at,
                exclude_reservation_id,
            )
        )
    )


def ensure_availability(
    db: Session,
    resource_id: int,
    start_at: datetime,
    end_at: datetime,
    exclude_reservation_id: int | None = None,
) -> None:
    conflicts = find_conflicts(
        db,
        resource_id,
        start_at,
        end_at,
        exclude_reservation_id,
    )
    if conflicts:
        raise AppError(
            409,
            "RESERVATION_CONFLICT",
            "El recurso ya tiene una reserva que se superpone con el horario solicitado.",
        )


def create_reservation(db: Session, payload: ReservationCreate) -> Reservation:
    resource = get_resource_or_error(db, payload.resource_id)
    get_customer_or_error(db, payload.customer_id)
    ensure_resource_is_active(resource)

    if payload.status not in {ReservationStatus.PENDING, ReservationStatus.CONFIRMED}:
        raise AppError(
            409,
            "INVALID_STATUS_TRANSITION",
            "Una reserva nueva solo puede estar pendiente o confirmada.",
        )

    start_at, end_at = validate_time_range(payload.start_at, payload.end_at)
    ensure_availability(db, payload.resource_id, start_at, end_at)

    reservation = Reservation(
        resource_id=payload.resource_id,
        customer_id=payload.customer_id,
        start_at=start_at,
        end_at=end_at,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


ALLOWED_TRANSITIONS: dict[ReservationStatus, set[ReservationStatus]] = {
    ReservationStatus.PENDING: {
        ReservationStatus.CONFIRMED,
        ReservationStatus.CANCELLED,
    },
    ReservationStatus.CONFIRMED: {
        ReservationStatus.COMPLETED,
        ReservationStatus.CANCELLED,
    },
    ReservationStatus.CANCELLED: set(),
    ReservationStatus.COMPLETED: set(),
}


def validate_status_transition(
    current: ReservationStatus, requested: ReservationStatus
) -> None:
    if current == requested:
        return
    if requested not in ALLOWED_TRANSITIONS[current]:
        raise AppError(
            409,
            "INVALID_STATUS_TRANSITION",
            f"No se puede cambiar una reserva de {current.value} a {requested.value}.",
        )


def update_reservation(
    db: Session, reservation: Reservation, payload: ReservationUpdate
) -> Reservation:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return reservation

    requested_status = changes.get("status", reservation.status)
    if (
        "status" in changes
        and reservation.status == ReservationStatus.CANCELLED
        and requested_status == ReservationStatus.CANCELLED
    ):
        raise AppError(
            409,
            "RESERVATION_ALREADY_CANCELLED",
            "La reserva ya se encuentra cancelada.",
        )
    validate_status_transition(reservation.status, requested_status)

    resource_id = changes.get("resource_id", reservation.resource_id)
    customer_id = changes.get("customer_id", reservation.customer_id)
    start_at = changes.get("start_at", reservation.start_at)
    end_at = changes.get("end_at", reservation.end_at)

    if "resource_id" in changes:
        get_resource_or_error(db, resource_id)
    if "customer_id" in changes:
        get_customer_or_error(db, customer_id)

    schedule_changed = bool({"resource_id", "start_at", "end_at"} & changes.keys())
    if schedule_changed:
        resource = get_resource_or_error(db, resource_id)
        ensure_resource_is_active(resource)
        start_at, end_at = validate_time_range(start_at, end_at)
        ensure_availability(
            db,
            resource_id,
            start_at,
            end_at,
            exclude_reservation_id=reservation.id,
        )

    for field, value in changes.items():
        setattr(reservation, field, value)

    if schedule_changed:
        reservation.start_at = start_at
        reservation.end_at = end_at
    if requested_status == ReservationStatus.CANCELLED:
        reservation.cancelled_at = utc_now()

    db.commit()
    db.refresh(reservation)
    return reservation


def cancel_reservation(db: Session, reservation: Reservation) -> Reservation:
    if reservation.status == ReservationStatus.CANCELLED:
        raise AppError(
            409,
            "RESERVATION_ALREADY_CANCELLED",
            "La reserva ya se encuentra cancelada.",
        )
    validate_status_transition(reservation.status, ReservationStatus.CANCELLED)
    reservation.status = ReservationStatus.CANCELLED
    reservation.cancelled_at = utc_now()
    db.commit()
    db.refresh(reservation)
    return reservation
