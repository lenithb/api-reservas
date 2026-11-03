from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.auth import AuthSession, create_access_token, verify_password
from app.exceptions import AppError
from app.models.user import User
from app.schemas.user import Token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: AuthSession
) -> Token:
    user = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    if user is None or not verify_password(form.password, user.hashed_password):
        raise AppError(
            401,
            "AUTH_INVALID_CREDENTIALS",
            "El email o la contraseña son incorrectos.",
        )
    if not user.is_active:
        raise AppError(403, "AUTH_USER_INACTIVE", "El usuario está desactivado.")

    token, expires_at = create_access_token(user.id)
    return Token(access_token=token, expires_at=expires_at, token_type="bearer")
