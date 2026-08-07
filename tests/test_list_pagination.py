import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_resource_list_filters_before_paginating(client: AsyncClient) -> None:
    resources = [
        ("Sala norte", "room"),
        ("Sala sur", "room"),
        ("Vehículo uno", "vehicle"),
    ]
    created_ids = []
    for name, resource_type in resources:
        response = await client.post(
            "/resources",
            json={
                "name": name,
                "resource_type": resource_type,
                "capacity": 4,
            },
        )
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    response = await client.get(
        "/resources",
        params={"resource_type": "room", "page": 2, "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["limit"] == 1
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == created_ids[1]
    assert body["items"][0]["name"] == "Sala sur"


async def test_customer_list_searches_before_paginating(client: AsyncClient) -> None:
    customers = [
        ("Ana Reserva", "ana@example.com"),
        ("Bruno Pérez", "bruno.reserva@example.com"),
        ("Carla Pérez", "carla@example.com"),
    ]
    created_ids = []
    for full_name, email in customers:
        response = await client.post(
            "/customers",
            json={"full_name": full_name, "email": email},
        )
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    response = await client.get(
        "/customers",
        params={"search": "RESERVA", "page": 2, "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["limit"] == 1
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == created_ids[1]
    assert body["items"][0]["full_name"] == "Bruno Pérez"


@pytest.mark.parametrize("path", ["/resources", "/customers"])
async def test_paginated_lists_reject_limits_over_one_hundred(
    client: AsyncClient, path: str
) -> None:
    response = await client.get(path, params={"limit": 101})

    assert response.status_code == 422
