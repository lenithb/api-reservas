from datetime import date, datetime, time, timedelta, timezone

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


def future_day() -> date:
    return (datetime.now(timezone.utc) + timedelta(days=3)).date()


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), timezone.utc)


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


async def test_date_filter_includes_reservations_overlapping_the_day(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    target_day = future_day()
    previous_day = target_day - timedelta(days=1)
    next_day = target_day + timedelta(days=1)

    await create_reservation(
        client,
        base_entities,
        at(previous_day, 20),
        at(previous_day, 21),
    )
    crossing_start_id = await create_reservation(
        client,
        base_entities,
        at(previous_day, 23, 30),
        at(target_day, 0, 30),
    )
    crossing_end_id = await create_reservation(
        client,
        base_entities,
        at(target_day, 23, 30),
        at(next_day, 0, 30),
    )
    await create_reservation(
        client,
        base_entities,
        at(next_day, 8),
        at(next_day, 9),
    )

    response = await client.get(
        "/reservations",
        params={
            "start_date": target_day.isoformat(),
            "end_date": target_day.isoformat(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [
        crossing_start_id,
        crossing_end_id,
    ]


async def test_date_filter_rejects_an_inverted_range(client: AsyncClient) -> None:
    start_date = future_day()
    response = await client.get(
        "/reservations",
        params={
            "start_date": start_date.isoformat(),
            "end_date": (start_date - timedelta(days=1)).isoformat(),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_FILTER_DATE_RANGE"


async def test_filter_reservations_by_series_id(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    start_at = at(future_day(), 10)
    recurring_response = await client.post(
        "/reservations/recurring",
        json={
            "resource_id": base_entities["resource_id"],
            "customer_id": base_entities["customer_id"],
            "start_at": start_at.isoformat(),
            "end_at": (start_at + timedelta(hours=1)).isoformat(),
            "status": "confirmed",
            "occurrences": 2,
        },
    )
    assert recurring_response.status_code == 201
    recurring_reservations = recurring_response.json()
    await create_reservation(
        client,
        base_entities,
        start_at + timedelta(days=1),
        start_at + timedelta(days=1, hours=1),
    )

    response = await client.get(
        "/reservations",
        params={"series_id": recurring_reservations[0]["series_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [
        item["id"] for item in recurring_reservations
    ]
