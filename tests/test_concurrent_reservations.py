"""Pruebas de concurrencia: dos reservas no pueden ocupar el mismo horario.

Estas pruebas atacan el problema real: entre la comprobación de disponibilidad
del servicio y el guardado de la reserva puede entrar otra petición. La
protección definitiva está en la restricción de exclusión de PostgreSQL, así
que aquí se comprueba que la base de datos, y no sólo el servicio, son la
fuente de verdad.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.exceptions import AppError
from app.models.customer import Customer
from app.models.resource import Resource
from app.schemas.reservation import ReservationCreate
from app.services import reservation_service
from app.services.reservation_service import create_reservation

pytestmark = pytest.mark.anyio

CONCURRENT_ATTEMPTS = 8
BARRIER_TIMEOUT_SECONDS = 30


def future_window() -> tuple[datetime, datetime]:
    """Un horario en el futuro, válido para el servicio."""
    start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        minute=0, second=0, microsecond=0
    )
    return start, start + timedelta(hours=1)


async def seed_resource_and_customer(engine: AsyncEngine) -> tuple[int, int]:
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, autoflush=False, expire_on_commit=False
    )
    async with session_factory() as db:
        resource = Resource(
            name="Recurso concurrente",
            resource_type="room",
            capacity=4,
            is_active=True,
        )
        customer = Customer(
            full_name="Cliente Concurrente", email="concurrente@example.com"
        )
        db.add_all([resource, customer])
        await db.commit()
        return resource.id, customer.id


async def insert_reservation_directly(
    db: AsyncSession,
    resource_id: int,
    customer_id: int,
    start_at: datetime,
    end_at: datetime,
) -> None:
    """Inserta una reserva saltándose la comprobación del servicio."""
    await db.execute(
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


async def test_database_rejects_overlapping_reservations(
    async_engine: AsyncEngine, clean_database: None
) -> None:
    """La restricción de exclusión de PostgreSQL es la que evita el solapamiento."""
    resource_id, customer_id = await seed_resource_and_customer(async_engine)
    start_at, end_at = future_window()
    session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, autoflush=False
    )

    async with session_factory() as db:
        await insert_reservation_directly(db, resource_id, customer_id, start_at, end_at)
        await db.commit()

    async with session_factory() as db:
        with pytest.raises(Exception) as error:
            await insert_reservation_directly(
                db, resource_id, customer_id, start_at, end_at
            )
            await db.commit()

    assert getattr(error.value.orig, "sqlstate", None) == "23P01"


async def test_only_one_reservation_is_created_when_requests_overlap(
    async_engine: AsyncEngine, clean_database: None
) -> None:
    """Varias peticiones simultáneas al mismo horario: sólo una se crea."""
    resource_id, customer_id = await seed_resource_and_customer(async_engine)
    start_at, end_at = future_window()
    session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, autoflush=False
    )

    barrier = asyncio.Barrier(CONCURRENT_ATTEMPTS)

    async def attempt() -> tuple[str, str]:
        async with session_factory() as db:
            # Todas las peticiones arrancan al mismo tiempo.
            await barrier.wait()
            try:
                reservation = await create_reservation(
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

    results = await asyncio.gather(
        *(attempt() for _ in range(CONCURRENT_ATTEMPTS))
    )

    created = [result for result in results if result[0] == "created"]
    rejected = [result for result in results if result[0] == "error"]

    assert len(created) == 1
    assert len(rejected) == CONCURRENT_ATTEMPTS - 1
    assert {code for _, code in rejected} == {"RESERVATION_CONFLICT"}


async def test_database_conflict_is_reported_as_reservation_conflict(
    async_engine: AsyncEngine,
    clean_database: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si la comprobación previa se salta, la base igual avisa con el mismo código.

    Se desactiva a propósito la comprobación de disponibilidad del servicio
    para simular la carrera: la petición llegó al guardado cuando otra
    reserva ya ocupaba el horario. La respuesta de la API tiene que ser la
    misma que devuelve la comprobación previa.
    """

    async def skip_availability(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(reservation_service, "ensure_availability", skip_availability)

    resource_id, customer_id = await seed_resource_and_customer(async_engine)
    start_at, end_at = future_window()
    session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, autoflush=False
    )

    async with session_factory() as db:
        await insert_reservation_directly(db, resource_id, customer_id, start_at, end_at)
        await db.commit()

    async with session_factory() as db:
        with pytest.raises(AppError) as error:
            await create_reservation(
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


async def test_only_one_reservation_is_created_when_requests_are_sent_at_the_same_time(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    """Ocho peticiones HTTP simultáneas al mismo horario: sólo una reserva."""
    start_at, end_at = future_window()
    payload = {
        "resource_id": base_entities["resource_id"],
        "customer_id": base_entities["customer_id"],
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "status": "confirmed",
    }

    responses = await asyncio.gather(
        *(client.post("/reservations", json=payload) for _ in range(CONCURRENT_ATTEMPTS))
    )

    created = [response for response in responses if response.status_code == 201]
    conflicts = [response for response in responses if response.status_code == 409]

    assert len(created) == 1
    assert len(conflicts) == CONCURRENT_ATTEMPTS - 1
    assert {
        response.json()["detail"]["code"] for response in conflicts
    } == {"RESERVATION_CONFLICT"}


async def test_cancelled_reservations_release_the_slot_at_database_level(
    async_engine: AsyncEngine, clean_database: None
) -> None:
    """Una reserva cancelada no bloquea el horario en la base de datos."""
    resource_id, customer_id = await seed_resource_and_customer(async_engine)
    start_at, end_at = future_window()
    session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, autoflush=False
    )

    async with session_factory() as db:
        await insert_reservation_directly(db, resource_id, customer_id, start_at, end_at)
        await db.commit()

    async with session_factory() as db:
        await db.execute(
            text("UPDATE reservations SET status = 'cancelled' WHERE resource_id = :id"),
            {"id": resource_id},
        )
        await db.commit()

    async with session_factory() as db:
        await insert_reservation_directly(db, resource_id, customer_id, start_at, end_at)
        await db.commit()

    async with session_factory() as db:
        result = await db.execute(
            text("SELECT COUNT(*) FROM reservations WHERE resource_id = :id"),
            {"id": resource_id},
        )
        total = result.scalar_one()

    assert total == 2
