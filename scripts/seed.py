from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models.customer import Customer
from app.models.resource import Resource
from app.schemas.reservation import ReservationCreate
from app.services.reservation_service import cancel_reservation, create_reservation


def future_datetime(days: int, hour: int) -> datetime:
    target_date = (datetime.now(timezone.utc) + timedelta(days=days)).date()
    return datetime.combine(target_date, time(hour=hour), timezone.utc)


def seed() -> None:
    with SessionLocal() as db:
        if db.scalar(select(Resource.id).limit(1)) is not None:
            print("La base ya contiene recursos. No se cargaron datos nuevos.")
            return

        resources = [
            Resource(
                name="Cancha Norte",
                description="Cancha deportiva cubierta",
                resource_type="sports_court",
                capacity=12,
                is_active=True,
            ),
            Resource(
                name="Consultorio 2",
                description="Consultorio de uso general",
                resource_type="office",
                capacity=4,
                is_active=True,
            ),
            Resource(
                name="Sala Jacarandá",
                description="Sala para reuniones pequeñas",
                resource_type="meeting_room",
                capacity=8,
                is_active=True,
            ),
        ]
        customers = [
            Customer(
                full_name="Ana Torres",
                email="ana.torres@example.com",
                phone="+54 381 555 0101",
            ),
            Customer(
                full_name="Bruno Díaz",
                email="bruno.diaz@example.com",
                phone=None,
            ),
            Customer(
                full_name="Carla Medina",
                email="carla.medina@example.com",
                phone="+54 381 555 0103",
            ),
        ]
        db.add_all(resources + customers)
        db.commit()

        first = create_reservation(
            db,
            ReservationCreate(
                resource_id=resources[0].id,
                customer_id=customers[0].id,
                start_at=future_datetime(7, 10),
                end_at=future_datetime(7, 11),
                status="confirmed",
                notes="entrenamiento semanal",
            ),
        )
        create_reservation(
            db,
            ReservationCreate(
                resource_id=resources[1].id,
                customer_id=customers[1].id,
                start_at=future_datetime(8, 14),
                end_at=future_datetime(8, 15),
                status="confirmed",
                notes="consulta de ejemplo",
            ),
        )
        cancelled = create_reservation(
            db,
            ReservationCreate(
                resource_id=resources[2].id,
                customer_id=customers[2].id,
                start_at=future_datetime(9, 16),
                end_at=future_datetime(9, 17),
                notes="reserva que será cancelada",
            ),
        )
        cancel_reservation(db, cancelled)
        print(
            f"Datos cargados. Primera reserva confirmada: {first.id}; "
            f"reserva cancelada: {cancelled.id}."
        )


if __name__ == "__main__":
    seed()
