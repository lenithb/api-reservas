from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth import AdminUser, AuthSession, CurrentUser, hash_password
from app.exceptions import AppError
from app.models.user import User
from app.schemas.user import UserCreate, UserPage, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def normalized_email(email: object) -> str:
    return str(email).strip().lower()


def ensure_user_email_is_available(
    db: AuthSession, email: str, exclude_user_id: int | None = None
) -> None:
    query = select(User.id).where(User.email == email)
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    if db.scalar(query.limit(1)) is not None:
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "El email ya está registrado.")


def count_active_admins(db: AuthSession) -> int:
    return int(
        db.scalar(
            select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))
        )
        or 0
    )


def ensure_admin_removal_is_allowed(db: AuthSession, user: User) -> None:
    """Evita quedar sin ningún administrador activo en el sistema."""
    if user.role == "admin" and user.is_active and count_active_admins(db) <= 1:
        raise AppError(
            409,
            "USER_LAST_ADMIN_NOT_ALLOWED",
            "No se puede desactivar o degradar al último administrador activo.",
        )


def ensure_user_or_error(db: AuthSession, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "El usuario no existe.")
    return user


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate, db: AuthSession, admin: AdminUser
) -> User:
    email = normalized_email(payload.email)
    ensure_user_email_is_available(db, email)
    user = User(
        full_name=payload.full_name,
        email=email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "El email ya está registrado.") from exc
    db.refresh(user)
    return user


@router.get("", response_model=UserPage)
async def list_users(
    db: AuthSession,
    admin: AdminUser,
    search: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserPage:
    filters = []
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(User.full_name.ilike(pattern) | User.email.ilike(pattern))

    total = db.scalar(select(func.count(User.id)).where(*filters)) or 0
    query = (
        select(User)
        .where(*filters)
        .order_by(User.id)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(db.scalars(query))
    return UserPage(items=items, page=page, limit=limit, total=total)


@router.get("/me", response_model=UserRead)
async def get_current_profile(current_user: CurrentUser) -> User:
    return current_user


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, db: AuthSession, admin: AdminUser) -> User:
    return ensure_user_or_error(db, user_id)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int, payload: UserUpdate, db: AuthSession, admin: AdminUser
) -> User:
    user = ensure_user_or_error(db, user_id)
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes:
        changes["email"] = normalized_email(changes["email"])
        ensure_user_email_is_available(db, changes["email"], user.id)
    if changes.get("password") is not None:
        changes["hashed_password"] = hash_password(changes["password"])
        del changes["password"]
    if "is_active" in changes and changes["is_active"] is False:
        if user.id == admin.id:
            raise AppError(
                409,
                "USER_SELF_DEACTIVATE_NOT_ALLOWED",
                "No se puede desactivar el propio usuario.",
            )
        ensure_admin_removal_is_allowed(db, user)
    if "role" in changes and changes["role"] != "admin" and user.is_active:
        ensure_admin_removal_is_allowed(db, user)

    for field, value in changes.items():
        setattr(user, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "El email ya está registrado.") from exc
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: AuthSession, admin: AdminUser) -> Response:
    user = ensure_user_or_error(db, user_id)
    if user.id == admin.id:
        raise AppError(
            409,
            "USER_SELF_DELETE_NOT_ALLOWED",
            "No se puede eliminar el propio usuario.",
        )
    ensure_admin_removal_is_allowed(db, user)
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
