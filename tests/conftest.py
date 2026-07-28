from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture
async def client(tmp_path: Path) -> AsyncGenerator[AsyncClient, None]:
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

    async def override_get_db() -> AsyncGenerator[Session, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()
    test_engine.dispose()


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
