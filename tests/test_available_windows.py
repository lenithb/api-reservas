from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


def search_start() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(days=3)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )


async def create_reservation(
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


def parsed(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def test_available_windows_respect_conflicts_and_minimum_duration(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = search_start()
    end_at = start_at + timedelta(hours=5)
    await create_reservation(
        client,
        base_entities,
        start_at + timedelta(hours=1),
        start_at + timedelta(hours=2),
    )
    await create_reservation(
        client,
        base_entities,
        start_at + timedelta(hours=2, minutes=30),
        start_at + timedelta(hours=3, minutes=30),
    )

    response = await client.get(
        f"/resources/{base_entities['resource_id']}/available-windows",
        params={
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "minimum_duration_minutes": 60,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["minimum_duration_minutes"] == 60
    assert [
        (parsed(window["start_at"]), parsed(window["end_at"]))
        for window in body["windows"]
    ] == [
        (start_at, start_at + timedelta(hours=1)),
        (start_at + timedelta(hours=3, minutes=30), end_at),
    ]


async def test_available_windows_can_exclude_current_reservation(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = search_start()
    end_at = start_at + timedelta(hours=1)
    reservation_id = await create_reservation(
        client, base_entities, start_at, end_at
    )

    occupied_response = await client.get(
        f"/resources/{base_entities['resource_id']}/available-windows",
        params={"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
    )
    excluded_response = await client.get(
        f"/resources/{base_entities['resource_id']}/available-windows",
        params={
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "exclude_reservation_id": reservation_id,
        },
    )

    assert occupied_response.status_code == 200
    assert occupied_response.json()["windows"] == []
    assert excluded_response.status_code == 200
    assert len(excluded_response.json()["windows"]) == 1
    assert parsed(excluded_response.json()["windows"][0]["start_at"]) == start_at
    assert parsed(excluded_response.json()["windows"][0]["end_at"]) == end_at


async def test_available_windows_reject_ranges_over_seven_days(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = search_start()
    response = await client.get(
        f"/resources/{base_entities['resource_id']}/available-windows",
        params={
            "start_at": start_at.isoformat(),
            "end_at": (start_at + timedelta(days=7, minutes=1)).isoformat(),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "AVAILABILITY_RANGE_TOO_LONG"


async def test_opening_hours_limit_reservations_and_available_windows(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    resource_id = base_entities["resource_id"]
    update_response = await client.patch(
        f"/resources/{resource_id}",
        json={"opening_time": "09:00:00", "closing_time": "17:00:00"},
    )
    assert update_response.status_code == 200

    start_at = search_start()
    before_opening_response = await client.post(
        "/reservations",
        json={
            "resource_id": resource_id,
            "customer_id": base_entities["customer_id"],
            "start_at": start_at.replace(hour=8).isoformat(),
            "end_at": start_at.replace(hour=9).isoformat(),
        },
    )
    windows_response = await client.get(
        f"/resources/{resource_id}/available-windows",
        params={
            "start_at": start_at.replace(hour=8).isoformat(),
            "end_at": start_at.replace(hour=18).isoformat(),
        },
    )

    assert before_opening_response.status_code == 409
    assert before_opening_response.json()["detail"]["code"] == "OUTSIDE_OPENING_HOURS"
    assert windows_response.status_code == 200
    assert [
        (parsed(window["start_at"]), parsed(window["end_at"]))
        for window in windows_response.json()["windows"]
    ] == [(start_at, start_at.replace(hour=17))]


async def test_available_resources_excludes_resources_outside_opening_hours(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    resource_id = base_entities["resource_id"]
    update_response = await client.patch(
        f"/resources/{resource_id}",
        json={"opening_time": "09:00:00", "closing_time": "17:00:00"},
    )
    assert update_response.status_code == 200

    start_at = search_start().replace(hour=18)
    response = await client.get(
        "/resources/available",
        params={
            "start_at": start_at.isoformat(),
            "end_at": (start_at + timedelta(hours=1)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert all(item["id"] != resource_id for item in response.json()["items"])
