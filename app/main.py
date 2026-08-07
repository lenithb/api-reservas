from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.exceptions import AppError, app_error_handler
from app.routers import customers, reservations, resources

app = FastAPI(
    title="Reservation API",
    version=__version__,
    description="API REST básica para administrar recursos, clientes y reservas.",
)

app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: object, exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "DATABASE_ERROR",
                "message": "No se pudo completar la operación en la base de datos.",
            }
        },
    )


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(resources.router)
app.include_router(customers.router)
app.include_router(reservations.router)
