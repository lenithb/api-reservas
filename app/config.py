"""Configuración centralizada de la aplicación.

Todo lo que se puede cambiar por entorno (conexión a la base, secretos de
autenticación, CORS, nivel de logs) vive acá y en un solo objeto `Settings`.
El resto del código lee de este objeto en lugar de consultar `os.getenv`.
"""

from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

DEFAULT_JWT_SECRET = "dev-secret-change-me-in-production-0001"
DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/api_reservas"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV"),
    )

    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        validation_alias=AliasChoices("DATABASE_URL", "APP_DATABASE_URL"),
    )
    test_database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TEST_DATABASE_URL", "APP_TEST_DATABASE_URL"),
    )

    jwt_secret: str = Field(
        default=DEFAULT_JWT_SECRET,
        validation_alias=AliasChoices("APP_JWT_SECRET", "JWT_SECRET"),
    )
    jwt_expires_minutes: int = Field(
        default=1440,
        ge=1,
        validation_alias=AliasChoices("APP_JWT_EXPIRES_MINUTES"),
    )
    login_max_attempts: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices("APP_LOGIN_MAX_ATTEMPTS"),
    )
    login_attempt_window_seconds: int = Field(
        default=300,
        ge=1,
        validation_alias=AliasChoices("APP_LOGIN_ATTEMPT_WINDOW_SECONDS"),
    )

    cors_origins: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("APP_CORS_ORIGINS"),
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias=AliasChoices("APP_LOG_LEVEL"),
    )
    log_json: bool = Field(
        default=False,
        validation_alias=AliasChoices("APP_LOG_JSON"),
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        """Acepta los orígenes separados por coma o como lista real."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def database_must_be_postgresql(cls, value: str) -> str:
        """La API usa PostgreSQL en todos los entornos, incluido el desarrollo."""
        if not value.startswith("postgresql"):
            raise ValueError(
                "DATABASE_URL debe apuntar a PostgreSQL "
                "(por ejemplo postgresql+psycopg://usuario:clave@host:puerto/base)."
            )
        return value

    @field_validator("test_database_url")
    @classmethod
    def test_database_must_be_postgresql(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("postgresql"):
            raise ValueError("TEST_DATABASE_URL debe apuntar a PostgreSQL.")
        return value

    @model_validator(mode="after")
    def secret_must_be_strong_in_production(self) -> "Settings":
        """En producción no se puede arrancar con el secreto de desarrollo."""
        if self.app_env == "production" and self.jwt_secret == DEFAULT_JWT_SECRET:
            raise ValueError(
                "APP_JWT_SECRET debe definirse con un valor propio antes de arrancar "
                "en producción."
            )
        return self

    @property
    def sqlalchemy_url(self) -> str:
        """URL de SQLAlchemy sin el driver, para herramientas como Alembic."""
        return self.database_url

    def database_url_for(self, driver: str) -> str:
        """Reemplaza el driver de la URL de la base de datos.

        Permite mantener una sola variable `DATABASE_URL` y usarla tanto con el
        driver asíncrono de la aplicación como con el síncrono de Alembic.
        """
        scheme, separator, rest = self.database_url.partition("://")
        if not separator:
            return self.database_url
        base_scheme = scheme.split("+", 1)[0]
        return f"{base_scheme}+{driver}://{rest}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
