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


async def ensure_user_email_is_available(
    db: AuthSession, email: str, exclude_user_id: int | None = None
) -> None:
    query = select(User.id).where(User.email == email)
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    if await db.scalar(query.limit(1)) is not None:
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "El email ya está registrado.")


async def count_active_admins(db: AuthSession) -> int:
    return int(
        await db.scalar(
            select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))
        )
        or 0
    )


async def ensure_admin_removal_is_allowed(db: AuthSession, user: User) -> None:
    """Evita quedar sin ningún administrador activo en el sistema."""
    if user.role == "admin" and user.is_active and await count_active_admins(db) <= 1:
        raise AppError(
            409,
            "USER_LAST_ADMIN_NOT_ALLOWED",
            "No se puede desactivar o degradar al último administrador activo.",
        )


async def ensure_user_or_error(db: AuthSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise AppError(404, "USER_NOT_FOUND", "El usuario no existe.")
    return user


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate, db: AuthSession, admin: AdminUser
) -> User:
    email = normalized_email(payload.email)
    await ensure_user_email_is_available(db, email)
    user = User(
        full_name=payload.full_name,
        email=email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "El email ya está registrado.") from exc
    await db.refresh(user)
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

    total = await db.scalar(select(func.count(User.id)).where(*filters)) or 0
    query = (
        select(User)
        .where(*filters)
        .order_by(User.id)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(await db.scalars(query))
    return UserPage(items=items, page=page, limit=limit, total=total)


@router.get("/me", response_model=UserRead)
async def get_current_profile(current_user: CurrentUser) -> User:
    return current_user


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, db: AuthSession, admin: AdminUser) -> User:
    return await ensure_user_or_error(db, user_id)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int, payload: UserUpdate, db: AuthSession, admin: AdminUser
) -> User:
    user = await ensure_user_or_error(db, user_id)
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes:
        changes["email"] = normalized_email(changes["email"])
        await ensure_user_email_is_available(db, changes["email"], user.id)
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
        await ensure_admin_removal_is_allowed(db, user)
    if "role" in changes and changes["role"] != "admin" and user.is_active:
        await ensure_admin_removal_is_allowed(db, user)

    for field, value in changes.items():
        setattr(user, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "El email ya está registrado.") from exc
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: AuthSession, admin: AdminUser) -> Response:
    user = await ensure_user_or_error(db, user_id)
    if user.id == admin.id:
        raise AppError(
            409,
            "USER_SELF_DELETE_NOT_ALLOWED",
            "No se puede eliminar el propio usuario.",
        )
    await ensure_admin_removal_is_allowed(db, user)
    await db.delete(user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
