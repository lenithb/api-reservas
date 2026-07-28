from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient, Response

pytestmark = pytest.mark.anyio


def base_time() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(days=3)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )


def reservation_data(
    entities: dict[str, int], start_at: datetime, end_at: datetime
) -> dict[str, object]:
    return {
        "resource_id": entities["resource_id"],
        "customer_id": entities["customer_id"],
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "status": "confirmed",
        "notes": "reserva para una prueba",
    }


async def create_existing_reservation(
    client: AsyncClient, entities: dict[str, int]
) -> dict[str, object]:
    start_at = base_time()
    response = await client.post(
        "/reservations",
        json=reservation_data(entities, start_at, start_at + timedelta(hours=1)),
    )
    assert response.status_code == 201
    return response.json()


def error_code(response: Response) -> str:
    return str(response.json()["detail"]["code"])


async def test_create_valid_reservation(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = base_time()
    response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            start_at,
            start_at + timedelta(hours=1),
        ),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "confirmed"
    assert response.json()["start_at"].endswith("Z")


async def test_reject_end_before_start(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = base_time()
    response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            start_at,
            start_at - timedelta(minutes=30),
        ),
    )

    assert response.status_code == 422
    assert error_code(response) == "INVALID_DATE_RANGE"


async def test_reject_reservation_in_the_past(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = datetime.now(timezone.utc) - timedelta(hours=2)
    response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            start_at,
            start_at + timedelta(hours=1),
        ),
    )

    assert response.status_code == 422
    assert error_code(response) == "RESERVATION_IN_PAST"


async def test_reject_reservation_shorter_than_thirty_minutes(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = base_time()
    response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            start_at,
            start_at + timedelta(minutes=29),
        ),
    )

    assert response.status_code == 422
    assert error_code(response) == "RESERVATION_TOO_SHORT"


async def test_reject_reservation_longer_than_eight_hours(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = base_time()
    response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            start_at,
            start_at + timedelta(hours=8, minutes=1),
        ),
    )

    assert response.status_code == 422
    assert error_code(response) == "RESERVATION_TOO_LONG"


async def test_detect_partial_overlap(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    await create_existing_reservation(client, base_entities)
    start_at = base_time() - timedelta(minutes=30)
    response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            start_at,
            start_at + timedelta(hours=1),
        ),
    )

    assert response.status_code == 409
    assert error_code(response) == "RESERVATION_CONFLICT"


async def test_detect_reservation_contained_in_another(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    await create_existing_reservation(client, base_entities)
    start_at = base_time() + timedelta(minutes=15)
    response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            start_at,
            start_at + timedelta(minutes=30),
        ),
    )

    assert response.status_code == 409
    assert error_code(response) == "RESERVATION_CONFLICT"


async def test_detect_reservation_that_contains_another(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    await create_existing_reservation(client, base_entities)
    start_at = base_time() - timedelta(minutes=30)
    response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            start_at,
            start_at + timedelta(hours=2),
        ),
    )

    assert response.status_code == 409
    assert error_code(response) == "RESERVATION_CONFLICT"


async def test_allow_adjacent_reservations(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    await create_existing_reservation(client, base_entities)
    before = base_time() - timedelta(hours=1)
    after = base_time() + timedelta(hours=1)

    before_response = await client.post(
        "/reservations",
        json=reservation_data(base_entities, before, base_time()),
    )
    after_response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            after,
            after + timedelta(hours=1),
        ),
    )

    assert before_response.status_code == 201
    assert after_response.status_code == 201


async def test_allow_time_previously_cancelled(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    reservation = await create_existing_reservation(client, base_entities)
    cancel_response = await client.post(f"/reservations/{reservation['id']}/cancel")
    replacement_response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            base_time(),
            base_time() + timedelta(hours=1),
        ),
    )

    assert cancel_response.status_code == 200
    assert replacement_response.status_code == 201


async def test_cancel_reservation(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    reservation = await create_existing_reservation(client, base_entities)
    response = await client.post(f"/reservations/{reservation['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancelled_at"] is not None


async def test_reject_second_cancellation(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    reservation = await create_existing_reservation(client, base_entities)
    await client.post(f"/reservations/{reservation['id']}/cancel")
    response = await client.post(f"/reservations/{reservation['id']}/cancel")

    assert response.status_code == 409
    assert error_code(response) == "RESERVATION_ALREADY_CANCELLED"


async def test_reject_reservation_for_inactive_resource(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    await client.patch(
        f"/resources/{base_entities['resource_id']}",
        json={"is_active": False},
    )
    start_at = base_time()
    response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            start_at,
            start_at + timedelta(hours=1),
        ),
    )

    assert response.status_code == 409
    assert error_code(response) == "RESOURCE_INACTIVE"


async def test_update_rechecks_availability(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    await create_existing_reservation(client, base_entities)
    second_start = base_time() + timedelta(hours=2)
    second_response = await client.post(
        "/reservations",
        json=reservation_data(
            base_entities,
            second_start,
            second_start + timedelta(hours=1),
        ),
    )
    second_id = second_response.json()["id"]

    response = await client.patch(
        f"/reservations/{second_id}",
        json={
            "start_at": (base_time() + timedelta(minutes=30)).isoformat(),
            "end_at": (base_time() + timedelta(hours=1, minutes=30)).isoformat(),
        },
    )

    assert response.status_code == 409
    assert error_code(response) == "RESERVATION_CONFLICT"


async def test_availability_returns_conflicting_reservation(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    reservation = await create_existing_reservation(client, base_entities)
    response = await client.get(
        f"/resources/{base_entities['resource_id']}/availability",
        params={
            "start_at": (base_time() + timedelta(minutes=15)).isoformat(),
            "end_at": (base_time() + timedelta(minutes=45)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["conflicting_reservations"][0]["id"] == reservation["id"]
