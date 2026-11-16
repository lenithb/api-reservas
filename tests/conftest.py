from collections.abc import AsyncGenerator, Iterator
from urllib.parse import urlsplit, urlunsplit

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth import create_access_token, hash_password
from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models.user import User

settings = get_settings()

TABLES_IN_CLEANUP_ORDER = ("reservations", "resources", "customers", "users")


def test_database_url() -> str:
    """URL de la base de datos reservada para las pruebas.

    Se puede definir con TEST_DATABASE_URL. Si no está, se deriva del nombre de
    la base de la aplicación agregando el sufijo `_test`, para no tocar nunca
    los datos de desarrollo.
    """
    if settings.test_database_url:
        return settings.test_database_url

    parts = urlsplit(settings.database_url)
    base_name = parts.path.lstrip("/") or "api_reservas"
    test_name = f"{base_name}_test"
    return urlunsplit(parts._replace(path=f"/{test_name}"))


def ensure_test_database_exists(url: str) -> None:
    """Crea la base de pruebas si todavía no existe."""
    parts = urlsplit(url)
    target = parts.path.lstrip("/")
    maintenance_url = urlunsplit(parts._replace(path="/postgres"))

    engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target},
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{target}"'))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def postgres_engine() -> Iterator[Engine]:
    """Motor contra la base de pruebas con el esquema ya creado."""
    url = test_database_url()
    ensure_test_database_exists(url)

    engine = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10)
    with engine.begin() as connection:
        # La restricción de exclusión necesita la extensión btree_gist.
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def clean_database(postgres_engine: Engine) -> Iterator[None]:
    """Deja las tablas vacías antes de cada prueba."""
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE TABLE "
                + ", ".join(TABLES_IN_CLEANUP_ORDER)
                + " RESTART IDENTITY CASCADE"
            )
        )
    yield


class ApiTestContext:
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
async def test_env(
    postgres_engine: Engine, clean_database: None
) -> AsyncGenerator[ApiTestContext, None]:
    testing_session = sessionmaker(
        bind=postgres_engine,
        autoflush=False,
        expire_on_commit=False,
    )

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
        yield ApiTestContext(
            test_client, admin_headers, user_headers, admin_id, regular_id
        )
    app.dependency_overrides.clear()


@pytest.fixture
async def client(test_env: ApiTestContext) -> AsyncGenerator[AsyncClient, None]:
    # Los tests existentes piden el cliente directamente y operan como admin.
    assert test_env.client is not None
    yield test_env.client


@pytest.fixture
def admin_headers(test_env: ApiTestContext) -> dict[str, str]:
    return test_env.admin_headers


@pytest.fixture
def user_headers(test_env: ApiTestContext) -> dict[str, str]:
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
