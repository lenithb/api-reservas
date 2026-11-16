from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime values must include a timezone")
        return value.astimezone(timezone.utc)

    def process_result_value(
        self, value: datetime | None, dialect: object
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


settings = get_settings()

DATABASE_URL = settings.database_url

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def get_db() -> AsyncGenerator[Session, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
