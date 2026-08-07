from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


def future_start() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(days=3)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )


async def create_resource(
    client: AsyncClient,
    name: str,
    resource_type: str,
    capacity: int,
    is_active: bool = True,
) -> int:
    response = await client.post(
        "/resources",
        json={
            "name": name,
            "resource_type": resource_type,
            "capacity": capacity,
            "is_active": is_active,
        },
    )
    assert response.status_code == 201
    return int(response.json()["id"])


async def reserve_base_resource(
    client: AsyncClient,
    entities: dict[str, int],
    start_at: datetime,
    end_at: datetime,
) -> int:
    response = await client.post(
        "/reservations",
        json={
            "resource_id": entities["resource_id"],
            "customer_id": entities["customer_id"],
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "status": "confirmed",
        },
    )
    assert response.status_code == 201
    return int(response.json()["id"])


async def test_search_available_resources_filters_and_paginates(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = future_start()
    end_at = start_at + timedelta(hours=1)
    await reserve_base_resource(client, base_entities, start_at, end_at)
    await create_resource(client, "Sala grande", "room", 10)
    second_available_id = await create_resource(client, "Sala mediana", "room", 8)
    await create_resource(client, "Sala pequeña", "room", 2)
    await create_resource(client, "Sala inactiva", "room", 20, is_active=False)
    await create_resource(client, "Vehículo", "vehicle", 12)

    response = await client.get(
        "/resources/available",
        params={
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "resource_type": "room",
            "min_capacity": 5,
            "page": 2,
            "limit": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["limit"] == 1
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [second_available_id]


async def test_cancelled_reservation_releases_resource_in_search(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = future_start()
    end_at = start_at + timedelta(hours=1)
    reservation_id = await reserve_base_resource(
        client, base_entities, start_at, end_at
    )
    cancel_response = await client.post(f"/reservations/{reservation_id}/cancel")
    assert cancel_response.status_code == 200

    response = await client.get(
        "/resources/available",
        params={
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "resource_type": "room",
            "min_capacity": 6,
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == base_entities["resource_id"]


async def test_available_search_can_exclude_current_reservation(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = future_start()
    end_at = start_at + timedelta(hours=1)
    reservation_id = await reserve_base_resource(
        client, base_entities, start_at, end_at
    )

    response = await client.get(
        "/resources/available",
        params={
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "exclude_reservation_id": reservation_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == base_entities["resource_id"]


async def test_available_search_rejects_unknown_excluded_reservation(
    client: AsyncClient,
) -> None:
    start_at = future_start()
    response = await client.get(
        "/resources/available",
        params={
            "start_at": start_at.isoformat(),
            "end_at": (start_at + timedelta(hours=1)).isoformat(),
            "exclude_reservation_id": 9999,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "RESERVATION_NOT_FOUND"
