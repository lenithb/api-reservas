from datetime import datetime, timedelta, timezone
from typing import Annotated

import anyio
import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.exceptions import AppError
from app.models.user import User

settings = get_settings()

JWT_SECRET = settings.jwt_secret
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRES_MINUTES = settings.jwt_expires_minutes

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


async def hash_password_async(password: str) -> str:
    """Calcula el hash en un hilo aparte.

    bcrypt es de uso intensivo de CPU: si se ejecutara en el event loop
    bloquearía todas las peticiones concurrentes mientras hashea.
    """
    return await anyio.to_thread.run_sync(hash_password, password)


async def verify_password_async(password: str, hashed_password: str) -> bool:
    """Verifica la contraseña en un hilo aparte, por la misma razón que el hash."""
    return await anyio.to_thread.run_sync(verify_password, password, hashed_password)


def create_access_token(
    user_id: int, expires_delta: timedelta | None = None
) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=TOKEN_EXPIRES_MINUTES)
    )
    token = jwt.encode(
        {"sub": str(user_id), "exp": expires_at},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return token, expires_at


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AppError(401, "AUTH_NOT_AUTHENTICATED", "No estás autenticado.") from exc
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise AppError(401, "AUTH_NOT_AUTHENTICATED", "No estás autenticado.")
    return int(subject)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if token is None:
        raise AppError(401, "AUTH_NOT_AUTHENTICATED", "No estás autenticado.")
    user_id = decode_token(token)
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "AUTH_NOT_AUTHENTICATED", "No estás autenticado.")
    return user


async def require_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    if current_user.role != "admin":
        raise AppError(
            403,
            "AUTH_ADMIN_REQUIRED",
            "Esta acción requiere un usuario con rol de administrador.",
        )
    return current_user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
AuthSession = Annotated[AsyncSession, Depends(get_db)]
