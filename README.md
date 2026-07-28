# Reservation API

Primera versión de una API REST genérica para administrar recursos reservables, clientes y reservas. Puede servir como base para canchas, consultorios, salas, habitaciones, vehículos o turnos profesionales.

El proyecto contiene únicamente backend. La prioridad de esta versión es ofrecer una base funcional y fácil de continuar, sin autenticación ni infraestructura avanzada.

## Tecnologías

- Python 3.12
- FastAPI
- SQLAlchemy 2
- SQLite
- Pydantic 2
- Alembic
- Uvicorn
- Pytest y HTTPX

## Estructura

```text
api-reservas/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── exceptions.py
│   ├── models/
│   │   ├── customer.py
│   │   ├── reservation.py
│   │   └── resource.py
│   ├── schemas/
│   │   ├── common.py
│   │   ├── customer.py
│   │   ├── reservation.py
│   │   └── resource.py
│   ├── routers/
│   │   ├── customers.py
│   │   ├── reservations.py
│   │   └── resources.py
│   └── services/
│       └── reservation_service.py
├── alembic/
│   ├── versions/
│   │   └── 20260728_0001_initial_schema.py
│   ├── env.py
│   └── script.py.mako
├── scripts/
│   └── seed.py
├── tests/
├── .env.example
├── .gitignore
├── alembic.ini
├── requirements.txt
└── README.md
```

Los routers reciben y devuelven datos HTTP. La lógica de fechas, disponibilidad, actualización y cancelación está en `reservation_service.py`. No se agregó una capa de repositorios para mantener sencilla esta primera versión.

## Requisitos

En Linux Mint se necesita Python 3.12 o una versión compatible, junto con los paquetes para crear entornos virtuales:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
python3 --version
```

## Crear el entorno virtual

Desde la raíz del proyecto:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Instalar dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Configuración

Copiar el archivo de ejemplo:

```bash
cp .env.example .env
```

El valor predeterminado es:

```env
DATABASE_URL=sqlite:///./reservations.db
```

La ruta relativa se resuelve desde el directorio en el que se ejecuta la aplicación.

## Migraciones

Crear o actualizar las tablas mediante Alembic:

```bash
alembic upgrade head
```

Consultar la migración aplicada:

```bash
alembic current
```

La aplicación no ejecuta `Base.metadata.create_all()` al iniciar. Alembic es el mecanismo principal para administrar el esquema. Las pruebas sí crean su esquema temporal directamente para mantener el aislamiento.

## Datos iniciales

Después de aplicar las migraciones, cargar tres recursos, tres clientes, dos reservas confirmadas y una cancelada:

```bash
python -m scripts.seed
```

El script evita volver a cargar los datos si la base ya contiene recursos.

## Ejecutar la API

```bash
uvicorn app.main:app --reload
```

La API queda disponible en `http://127.0.0.1:8000`.

## Swagger

- Swagger UI: `http://127.0.0.1:8000/docs`
- Esquema OpenAPI: `http://127.0.0.1:8000/openapi.json`

## Ejecutar las pruebas

```bash
pytest
```

Las pruebas usan un archivo SQLite temporal separado para cada caso. Cubren creación, rangos inválidos, duraciones, distintos tipos de superposición, horarios contiguos, cancelaciones, recursos inactivos y actualización con nueva comprobación de disponibilidad.

## Endpoints

### Salud

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Comprueba que la API responde |

### Recursos

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/resources` | Crea un recurso |
| `GET` | `/resources` | Lista recursos |
| `GET` | `/resources/{resource_id}` | Obtiene un recurso |
| `PATCH` | `/resources/{resource_id}` | Actualiza parcialmente un recurso |
| `DELETE` | `/resources/{resource_id}` | Elimina un recurso sin reservas |
| `GET` | `/resources/{resource_id}/availability` | Consulta disponibilidad entre dos fechas |

El listado acepta `resource_type` e `is_active`.

La disponibilidad recibe `start_at` y `end_at` en formato ISO 8601. Devuelve `available` y las reservas activas que generan el conflicto.

### Clientes

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/customers` | Crea un cliente |
| `GET` | `/customers` | Lista clientes |
| `GET` | `/customers/{customer_id}` | Obtiene un cliente |
| `PATCH` | `/customers/{customer_id}` | Actualiza parcialmente un cliente |
| `DELETE` | `/customers/{customer_id}` | Elimina un cliente sin reservas |

El parámetro `search` busca coincidencias parciales en el nombre o email.

### Reservas

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/reservations` | Crea una reserva |
| `GET` | `/reservations` | Lista reservas con paginación |
| `GET` | `/reservations/{reservation_id}` | Obtiene una reserva |
| `PATCH` | `/reservations/{reservation_id}` | Actualiza una reserva |
| `POST` | `/reservations/{reservation_id}/cancel` | Cancela una reserva |

El listado acepta `resource_id`, `customer_id`, `status`, `start_date`, `end_date`, `page` y `limit`. `start_date` y `end_date` filtran por la fecha de inicio de la reserva. `limit` admite entre 1 y 100 elementos.

La respuesta paginada tiene esta forma:

```json
{
  "items": [],
  "page": 1,
  "limit": 20,
  "total": 0
}
```

## Fechas y zona horaria

Las fechas de reservas deben incluir una zona horaria. Por ejemplo:

```text
2026-08-01T10:00:00-03:00
```

Antes de guardar o comparar, la API normaliza las fechas a UTC. Las respuestas también se entregan en UTC y pueden verse con el sufijo `Z`:

```text
2026-08-01T13:00:00Z
```

No se aceptan fechas sin zona horaria. Esta versión no permite configurar zonas horarias diferentes por recurso o cliente.

## Reglas de reservas

- `start_at` debe ser anterior a `end_at`.
- Una reserva nueva no puede comenzar en el pasado.
- La duración mínima es de 30 minutos.
- La duración máxima es de 8 horas.
- Un recurso inactivo no acepta reservas nuevas ni cambios de horario.
- Dos reservas no canceladas no pueden superponerse sobre un mismo recurso.
- Una reserva que termina exactamente cuando comienza otra no produce conflicto.
- Las reservas canceladas liberan el horario.
- Al cambiar recurso, inicio o final se vuelve a consultar la disponibilidad y se excluye la propia reserva.
- Las reservas no se eliminan físicamente desde la API.
- Un recurso o cliente con reservas asociadas no puede eliminarse, incluso si esas reservas están canceladas.

Los estados disponibles son `pending`, `confirmed`, `cancelled` y `completed`. Las transiciones implementadas son:

```text
pending -> confirmed | cancelled
confirmed -> completed | cancelled
cancelled -> estado final
completed -> estado final
```

Las reservas nuevas solo pueden crearse como `pending` o `confirmed`.

## Errores

Las reglas de negocio usan un código estable y un mensaje legible. Por ejemplo:

```json
{
  "detail": {
    "code": "RESERVATION_CONFLICT",
    "message": "El recurso ya tiene una reserva que se superpone con el horario solicitado."
  }
}
```

Se contemplan entidades inexistentes, email duplicado, fechas inválidas, recurso inactivo, conflicto de horario, eliminación no permitida y transición de estado inválida. Los errores internos de SQLAlchemy no se incluyen en la respuesta.

## Limitaciones actuales

- SQLite es adecuado para desarrollo y una carga pequeña, no para alta concurrencia.
- La comprobación de superposición se hace en el servicio y no cuenta todavía con una garantía transaccional fuerte ante solicitudes simultáneas.
- Los handlers son asíncronos, pero usan SQLAlchemy síncrono; una futura versión con mayor carga debería adoptar sesiones asíncronas o mover el trabajo bloqueante a workers.
- No hay autenticación, usuarios, roles ni permisos.
- No hay horarios de apertura, días no laborables ni reservas recurrentes.
- No existen pagos, precios, cupones, notificaciones ni recordatorios.
- No hay reservas temporales, lista de espera ni calendario visual.
- No se incluyen frontend, Docker, PostgreSQL, Redis, Celery ni configuración de producción.

## Próximas mejoras posibles

- Incorporar autenticación y permisos en una fase posterior.
- Usar PostgreSQL y reforzar el control de concurrencia.
- Agregar reglas de apertura y días no laborables.
- Mejorar filtros y ordenamiento sin convertirlos todavía en un sistema genérico complejo.
- Añadir reservas recurrentes, recordatorios y notificaciones cuando el dominio lo requiera.
- Preparar configuración, observabilidad y despliegue para producción.

Estas mejoras no forman parte de la primera versión incluida en este repositorio.
