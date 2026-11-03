from collections.abc import AsyncGenerator
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import create_access_token
from app.main import app
from tests.conftest import TestEnvironment

pytestmark = pytest.mark.anyio


@pytest.fixture
async def anonymous_client(test_env: TestEnvironment) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as no_auth_client:
        yield no_auth_client


async def test_health_is_public(anonymous_client: AsyncClient) -> None:
    response = await anonymous_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_protected_endpoint_rejects_missing_token(
    anonymous_client: AsyncClient,
) -> None:
    response = await anonymous_client.get("/resources")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_NOT_AUTHENTICATED"
    assert response.headers["www-authenticate"] == "Bearer"


async def test_protected_endpoint_rejects_invalid_token(
    anonymous_client: AsyncClient,
) -> None:
    response = await anonymous_client.get(
        "/resources", headers={"Authorization": "Bearer no-es-un-token"}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_NOT_AUTHENTICATED"


async def test_rejected_expired_token(
    test_env: TestEnvironment, anonymous_client: AsyncClient
) -> None:
    expired_token, _expires_at = create_access_token(
        test_env.admin_id, expires_delta=timedelta(seconds=-30)
    )

    response = await anonymous_client.get(
        "/resources", headers={"Authorization": f"Bearer {expired_token}"}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_NOT_AUTHENTICATED"


async def test_login_returns_usable_token(
    test_env: TestEnvironment, anonymous_client: AsyncClient
) -> None:
    login_response = await anonymous_client.post(
        "/auth/login",
        data={"username": "admin@example.com", "password": "admin-password-1"},
    )

    assert login_response.status_code == 200
    payload = login_response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]

    resources_response = await anonymous_client.get(
        "/resources",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert resources_response.status_code == 200


async def test_login_rejects_wrong_password(anonymous_client: AsyncClient) -> None:
    response = await anonymous_client.post(
        "/auth/login",
        data={"username": "admin@example.com", "password": "clave-incorrecta"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_INVALID_CREDENTIALS"


async def test_login_rejects_unknown_email(anonymous_client: AsyncClient) -> None:
    response = await anonymous_client.post(
        "/auth/login",
        data={"username": "nadie@example.com", "password": "lo-que-sea"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_INVALID_CREDENTIALS"


async def test_regular_user_cannot_manage_resources(test_env: TestEnvironment) -> None:
    response = await test_env.client.post(
        "/resources",
        json={
            "name": "Recurso sin permiso",
            "description": None,
            "resource_type": "room",
            "capacity": 2,
            "is_active": True,
        },
        headers=test_env.user_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTH_ADMIN_REQUIRED"


async def test_regular_user_can_list_resources(test_env: TestEnvironment) -> None:
    response = await test_env.client.get("/resources", headers=test_env.user_headers)

    assert response.status_code == 200


async def test_regular_user_cannot_list_users(test_env: TestEnvironment) -> None:
    response = await test_env.client.get("/users", headers=test_env.user_headers)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTH_ADMIN_REQUIRED"


async def test_regular_user_cannot_delete_customers(test_env: TestEnvironment) -> None:
    response = await test_env.client.delete(
        "/customers/1", headers=test_env.user_headers
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTH_ADMIN_REQUIRED"


async def test_current_profile(test_env: TestEnvironment) -> None:
    response = await test_env.client.get("/users/me", headers=test_env.user_headers)

    assert response.status_code == 200
    profile = response.json()
    assert profile["email"] == "usuario@example.com"
    assert profile["role"] == "user"
    assert "hashed_password" not in profile


async def test_admin_can_create_and_list_users(test_env: TestEnvironment) -> None:
    create_response = await test_env.client.post(
        "/users",
        json={
            "full_name": "Recepción",
            "email": "recepcion@example.com",
            "password": "recepcion-1234",
            "role": "user",
        },
    )
    assert create_response.status_code == 201
    assert create_response.json()["role"] == "user"

    list_response = await test_env.client.get("/users")
    assert list_response.status_code == 200
    emails = [item["email"] for item in list_response.json()["items"]]
    assert "recepcion@example.com" in emails


async def test_admin_cannot_create_duplicate_user(test_env: TestEnvironment) -> None:
    response = await test_env.client.post(
        "/users",
        json={
            "full_name": "Duplicado",
            "email": "admin@example.com",
            "password": "duplicado-1234",
            "role": "user",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "EMAIL_ALREADY_EXISTS"


async def test_created_user_reports_missing_password(anonymous_client: AsyncClient) -> None:
    response = await anonymous_client.post("/users", json={"full_name": "X"})

    assert response.status_code == 401


async def test_deactivated_user_token_is_rejected(test_env: TestEnvironment) -> None:
    deactivate = await test_env.client.patch(
        f"/users/{test_env.regular_id}", json={"is_active": False}
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False

    response = await test_env.client.get("/resources", headers=test_env.user_headers)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_NOT_AUTHENTICATED"


async def test_last_active_admin_cannot_be_demoted(test_env: TestEnvironment) -> None:
    demote = await test_env.client.patch(
        f"/users/{test_env.admin_id}", json={"role": "user"}
    )

    assert demote.status_code == 409
    assert demote.json()["detail"]["code"] == "USER_LAST_ADMIN_NOT_ALLOWED"


async def test_admin_cannot_deactivate_self(test_env: TestEnvironment) -> None:
    response = await test_env.client.patch(
        f"/users/{test_env.admin_id}", json={"is_active": False}
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]["code"] == "USER_SELF_DEACTIVATE_NOT_ALLOWED"
    )


async def test_admin_cannot_delete_self(test_env: TestEnvironment) -> None:
    response = await test_env.client.delete(f"/users/{test_env.admin_id}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "USER_SELF_DELETE_NOT_ALLOWED"


async def test_admin_can_delete_secondary_user(test_env: TestEnvironment) -> None:
    create_response = await test_env.client.post(
        "/users",
        json={
            "full_name": "Temporal",
            "email": "temporal@example.com",
            "password": "temporal-1234",
            "role": "user",
        },
    )
    created_id = create_response.json()["id"]

    delete_response = await test_env.client.delete(f"/users/{created_id}")
    assert delete_response.status_code == 204

    get_response = await test_env.client.get(f"/users/{created_id}")
    assert get_response.status_code == 404
    assert get_response.json()["detail"]["code"] == "USER_NOT_FOUND"
