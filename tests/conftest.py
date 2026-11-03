from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models.user import User


class TestEnvironment:
    def __init__(
        self,
        client: AsyncClient,
        admin_headers: dict[str, str],
        user_headers: dict[str, str],
        admin_id: int,
        regular_id: int,
    ) -> None:
        self.client = client
        self.admin_headers = admin_headers
        self.user_headers = user_headers
        self.admin_id = admin_id
        self.regular_id = regular_id


@pytest.fixture
async def test_env(tmp_path: Path) -> AsyncGenerator[TestEnvironment, None]:
    database_path = tmp_path / "test_reservations.db"
    test_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=test_engine)

    with testing_session() as db:
        admin = User(
            full_name="Administrador de prueba",
            email="admin@example.com",
            hashed_password=hash_password("admin-password-1"),
            role="admin",
        )
        regular = User(
            full_name="Usuario de prueba",
            email="usuario@example.com",
            hashed_password=hash_password("usuario-password-1"),
            role="user",
        )
        db.add_all([admin, regular])
        db.commit()
        admin_id, regular_id = admin.id, regular.id

    admin_token, _ = create_access_token(admin_id)
    user_token, _ = create_access_token(regular_id)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    user_headers = {"Authorization": f"Bearer {user_token}"}

    async def override_get_db() -> AsyncGenerator[Session, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=admin_headers,
    ) as test_client:
        yield TestEnvironment(test_client, admin_headers, user_headers, admin_id, regular_id)
    app.dependency_overrides.clear()
    test_engine.dispose()


@pytest.fixture
async def client(test_env: TestEnvironment) -> AsyncGenerator[AsyncClient, None]:
    # Los tests existentes piden el cliente directamente y operan como admin.
    assert test_env.client is not None
    yield test_env.client


@pytest.fixture
def admin_headers(test_env: TestEnvironment) -> dict[str, str]:
    return test_env.admin_headers


@pytest.fixture
def user_headers(test_env: TestEnvironment) -> dict[str, str]:
    return test_env.user_headers


@pytest.fixture
async def base_entities(client: AsyncClient) -> dict[str, int]:
    resource_response = await client.post(
        "/resources",
        json={
            "name": "Sala de prueba",
            "description": "Recurso creado para los tests",
            "resource_type": "room",
            "capacity": 6,
            "is_active": True,
        },
    )
    customer_response = await client.post(
        "/customers",
        json={
            "full_name": "Cliente de Prueba",
            "email": "cliente@example.com",
            "phone": None,
        },
    )
    assert resource_response.status_code == 201
    assert customer_response.status_code == 201
    return {
        "resource_id": resource_response.json()["id"],
        "customer_id": customer_response.json()["id"],
    }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
