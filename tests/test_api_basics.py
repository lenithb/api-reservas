import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_openapi_exposes_current_version(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["version"] == "0.2.0"


async def test_duplicate_customer_email_is_rejected(client: AsyncClient) -> None:
    payload = {
        "full_name": "Primera Persona",
        "email": "repetido@example.com",
    }
    first_response = await client.post("/customers", json=payload)
    assert first_response.status_code == 201

    response = await client.post(
        "/customers",
        json={"full_name": "Segunda Persona", "email": "REPETIDO@example.com"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EMAIL_ALREADY_EXISTS"


async def test_reservation_list_is_paginated(
    client: AsyncClient, base_entities: dict[str, int]
) -> None:
    response = await client.get("/reservations", params={"page": 1, "limit": 10})

    assert response.status_code == 200
    assert response.json() == {"items": [], "page": 1, "limit": 10, "total": 0}
