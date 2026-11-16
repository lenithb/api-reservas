"""Pruebas de concurrencia: dos reservas no pueden ocupar el mismo horario.

Estas pruebas atacan el problema real: entre la comprobación de disponibilidad
del servicio y el guardado de la reserva puede entrar otra petición. La
protección definitiva está en la restricción de exclusión de PostgreSQL, así
que aquí se comprueba que la base de datos, y no sólo el servicio, son la
fuente de verdad.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.exceptions import AppError
from app.models.customer import Customer
from app.models.resource import Resource
from app.schemas.reservation import ReservationCreate
from app.services import reservation_service
from app.services.reservation_service import create_reservation

CONCURRENT_ATTEMPTS = 8
BARRIER_TIMEOUT_SECONDS = 30


def future_window() -> tuple[datetime, datetime]:
    """Un horario en el futuro, válido para el servicio."""
    start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        minute=0, second=0, microsecond=0
    )
    return start, start + timedelta(hours=1)


def seed_resource_and_customer(engine: Engine) -> tuple[int, int]:
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as db:
        resource = Resource(
            name="Recurso concurrente",
            resource_type="room",
            capacity=4,
            is_active=True,
        )
        customer = Customer(full_name="Cliente Concurrente", email="concurrente@example.com")
        db.add_all([resource, customer])
        db.commit()
        return resource.id, customer.id


def insert_reservation_directly(
    db: Session, resource_id: int, customer_id: int, start_at: datetime, end_at: datetime
) -> None:
    """Inserta una reserva saltándose la comprobación del servicio."""
    db.execute(
        text(
            """
            INSERT INTO reservations (
                resource_id, customer_id, start_at, end_at, status, created_at, updated_at
            ) VALUES (
                :resource_id, :customer_id, :start_at, :end_at, 'confirmed', NOW(), NOW()
            )
            """
        ),
        {
            "resource_id": resource_id,
            "customer_id": customer_id,
            "start_at": start_at,
            "end_at": end_at,
        },
    )


def test_database_rejects_overlapping_reservations(
    postgres_engine: Engine, clean_database: None
) -> None:
    """La restricción de exclusión de PostgreSQL es la que evita el solapamiento."""
    resource_id, customer_id = seed_resource_and_customer(postgres_engine)
    start_at, end_at = future_window()
    session_factory = sessionmaker(bind=postgres_engine, autoflush=False)

    with session_factory() as db:
        insert_reservation_directly(db, resource_id, customer_id, start_at, end_at)
        db.commit()

    with session_factory() as db:
        with pytest.raises(IntegrityError) as error:
            insert_reservation_directly(
                db, resource_id, customer_id, start_at, end_at
            )
            db.commit()

    assert error.value.orig.sqlstate == "23P01"


def test_only_one_reservation_is_created_when_requests_overlap(
    postgres_engine: Engine, clean_database: None
) -> None:
    """Varias peticiones simultáneas al mismo horario: sólo una se crea."""
    resource_id, customer_id = seed_resource_and_customer(postgres_engine)
    start_at, end_at = future_window()
    session_factory = sessionmaker(bind=postgres_engine, autoflush=False)

    barrier = Barrier(CONCURRENT_ATTEMPTS)

    def attempt() -> tuple[str, str]:
        with session_factory() as db:
            # Todas las peticiones arrancan al mismo tiempo.
            barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
            try:
                reservation = create_reservation(
                    db,
                    ReservationCreate(
                        resource_id=resource_id,
                        customer_id=customer_id,
                        start_at=start_at,
                        end_at=end_at,
                        status="confirmed",
                    ),
                )
                return "created", str(reservation.id)
            except AppError as error:
                return "error", error.code

    with ThreadPoolExecutor(max_workers=CONCURRENT_ATTEMPTS) as pool:
        results = list(pool.map(lambda _: attempt(), range(CONCURRENT_ATTEMPTS)))

    created = [result for result in results if result[0] == "created"]
    rejected = [result for result in results if result[0] == "error"]

    assert len(created) == 1
    assert len(rejected) == CONCURRENT_ATTEMPTS - 1
    assert {code for _, code in rejected} == {"RESERVATION_CONFLICT"}


def test_database_conflict_is_reported_as_reservation_conflict(
    postgres_engine: Engine, clean_database: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si la comprobación previa se salta, la base igual avisa con el mismo código.

    Se desactiva a propósito la comprobación de disponibilidad del servicio
    para simular la carrera: la petición llegó al guardado cuando otra
    reserva ya ocupaba el horario. La respuesta de la API tiene que ser la
    misma que devuelve la comprobación previa.
    """
    monkeypatch.setattr(
        reservation_service, "ensure_availability", lambda *args, **kwargs: None
    )

    resource_id, customer_id = seed_resource_and_customer(postgres_engine)
    start_at, end_at = future_window()
    session_factory = sessionmaker(bind=postgres_engine, autoflush=False)

    with session_factory() as db:
        insert_reservation_directly(db, resource_id, customer_id, start_at, end_at)
        db.commit()

    with session_factory() as db:
        with pytest.raises(AppError) as error:
            create_reservation(
                db,
                ReservationCreate(
                    resource_id=resource_id,
                    customer_id=customer_id,
                    start_at=start_at,
                    end_at=end_at,
                    status="confirmed",
                ),
            )

    assert error.value.code == "RESERVATION_CONFLICT"
    assert error.value.status_code == 409


def test_cancelled_reservations_release_the_slot_at_database_level(
    postgres_engine: Engine, clean_database: None
) -> None:
    """Una reserva cancelada no bloquea el horario en la base de datos."""
    resource_id, customer_id = seed_resource_and_customer(postgres_engine)
    start_at, end_at = future_window()
    session_factory = sessionmaker(bind=postgres_engine, autoflush=False)

    with session_factory() as db:
        insert_reservation_directly(db, resource_id, customer_id, start_at, end_at)
        db.commit()

    with session_factory() as db:
        db.execute(
            text("UPDATE reservations SET status = 'cancelled' WHERE resource_id = :id"),
            {"id": resource_id},
        )
        db.commit()

    with session_factory() as db:
        insert_reservation_directly(db, resource_id, customer_id, start_at, end_at)
        db.commit()

    with session_factory() as db:
        total = db.execute(
            text("SELECT COUNT(*) FROM reservations WHERE resource_id = :id"),
            {"id": resource_id},
        ).scalar_one()

    assert total == 2
