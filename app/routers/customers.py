from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.exceptions import AppError
from app.models.customer import Customer
from app.models.reservation import Reservation
from app.schemas.customer import CustomerCreate, CustomerPage, CustomerRead, CustomerUpdate
from app.services.reservation_service import get_customer_or_error

router = APIRouter(prefix="/customers", tags=["customers"])
DbSession = Annotated[Session, Depends(get_db)]


def normalized_email(email: object) -> str:
    return str(email).strip().lower()


def ensure_email_is_available(
    db: Session, email: str, exclude_customer_id: int | None = None
) -> None:
    query = select(Customer.id).where(Customer.email == email)
    if exclude_customer_id is not None:
        query = query.where(Customer.id != exclude_customer_id)
    if db.scalar(query.limit(1)) is not None:
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "El email ya está registrado.")


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(payload: CustomerCreate, db: DbSession) -> Customer:
    email = normalized_email(payload.email)
    ensure_email_is_available(db, email)
    customer = Customer(
        full_name=payload.full_name,
        email=email,
        phone=payload.phone,
    )
    db.add(customer)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "El email ya está registrado.") from exc
    db.refresh(customer)
    return customer


@router.get("", response_model=CustomerPage)
async def list_customers(
    db: DbSession,
    search: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CustomerPage:
    filters = []
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(Customer.full_name.ilike(pattern), Customer.email.ilike(pattern))
        )

    total = db.scalar(select(func.count(Customer.id)).where(*filters)) or 0
    query = (
        select(Customer)
        .where(*filters)
        .order_by(Customer.id)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(db.scalars(query))
    return CustomerPage(items=items, page=page, limit=limit, total=total)


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(customer_id: int, db: DbSession) -> Customer:
    return get_customer_or_error(db, customer_id)


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: int, payload: CustomerUpdate, db: DbSession
) -> Customer:
    customer = get_customer_or_error(db, customer_id)
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes:
        changes["email"] = normalized_email(changes["email"])
        ensure_email_is_available(db, changes["email"], customer.id)
    for field, value in changes.items():
        setattr(customer, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "El email ya está registrado.") from exc
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(customer_id: int, db: DbSession) -> Response:
    customer = get_customer_or_error(db, customer_id)
    has_reservations = db.scalar(
        select(Reservation.id).where(Reservation.customer_id == customer_id).limit(1)
    )
    if has_reservations is not None:
        raise AppError(
            409,
            "CUSTOMER_DELETE_NOT_ALLOWED",
            "No se puede eliminar un cliente que tiene reservas asociadas.",
        )
    db.delete(customer)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
