# API de reservas

La versión actual es `v0.4.0`. Esta API REST permite manejar recursos, clientes y reservas, y sirve como punto de partida para distintos casos: una cancha, un consultorio, una sala, una habitación, un vehículo o cualquier otra cosa que se pueda reservar por horario.

Es un proyecto solamente de backend. Por ahora busco resolver bien lo esencial: crear reservas, evitar cruces de horarios y permitir cancelaciones. Todavía no tiene autenticación ni componentes pensados para producción, así que queda bastante lugar para seguir practicando y mejorándolo.

Los cambios de cada versión están documentados en [CHANGELOG.md](CHANGELOG.md).

## Qué se puede hacer

- Crear, consultar, editar y eliminar recursos reservables.
- Crear y administrar clientes.
- Registrar reservas con estados `pending`, `confirmed`, `cancelled` y `completed`.
- Consultar si un recurso está disponible en un rango de fechas.
- Buscar recursos disponibles por horario, tipo y capacidad mínima.
- Configurar un horario diario de apertura para cada recurso.
- Marcar fechas puntuales en las que un recurso no está disponible.
- Crear series de reservas recurrentes semanales.
- Evitar reservas superpuestas sobre el mismo recurso.
- Cancelar una reserva sin borrarla de la base de datos.
- Filtrar recursos, clientes y reservas.
- Paginar los listados de recursos, clientes y reservas.

## Tecnologías

- Python 3.12
- FastAPI
- SQLAlchemy 2
- SQLite
- Pydantic 2
- Alembic
- Uvicorn
- Pytest y HTTPX

## Cómo ponerlo en marcha

Los siguientes comandos están pensados para Linux Mint y deben ejecutarse desde la raíz del proyecto.

Primero hay que tener instalados Python, Pip y el módulo para crear entornos virtuales:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
python3 --version
```

Después se crea y activa el entorno virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Con el entorno activo, se instalan las dependencias:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Configuración

El proyecto trae un archivo de ejemplo para la configuración:

```bash
cp .env.example .env
```

En esta versión solamente se configura la conexión a SQLite:

```env
DATABASE_URL=sqlite:///./reservations.db
```

El archivo `reservations.db` se crea en la raíz del proyecto y está ignorado por Git.

## Crear la base de datos

Alembic se encarga de crear y actualizar las tablas:

```bash
alembic upgrade head
```

Si quieres comprobar qué migración está aplicada:

```bash
alembic current
```

La aplicación no crea las tablas automáticamente cuando arranca. Eso queda a cargo de Alembic para que los cambios futuros del esquema puedan manejarse con migraciones.

## Cargar algunos datos de ejemplo

Hay un script pequeño que agrega tres recursos, tres clientes, dos reservas confirmadas y una reserva cancelada:

```bash
python -m scripts.seed
```

Si la base ya contiene recursos, el script no vuelve a insertar los datos.

## Ejecutar la API

```bash
uvicorn app.main:app --reload
```

La API quedará escuchando en:

```text
http://127.0.0.1:8000
```

FastAPI genera la documentación interactiva automáticamente:

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`

## Ejecutar las pruebas

```bash
pytest
```

Las pruebas usan una base SQLite temporal y separada de la base local. Los casos principales cubren fechas incorrectas, límites de duración, distintos tipos de superposición, horarios contiguos, cancelaciones, recursos inactivos y cambios de horario en una reserva existente.

## Estructura del proyecto

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
│   └── versions/
├── scripts/
│   └── seed.py
├── tests/
├── .env.example
├── CHANGELOG.md
├── alembic.ini
├── requirements.txt
└── README.md
```

Los routers se ocupan de las peticiones HTTP. Las reglas relacionadas con fechas, disponibilidad, actualización y cancelación viven en `reservation_service.py`. Para no complicar de más esta etapa, no se agregó una capa de repositorios.

## Endpoints disponibles

### Estado de la API

| Método | Ruta      | Para qué sirve                        |
| ------ | --------- | ------------------------------------- |
| `GET`  | `/health` | Comprueba que la API está funcionando |

### Recursos

| Método   | Ruta                                    | Para qué sirve                            |
| -------- | --------------------------------------- | ----------------------------------------- |
| `POST`   | `/resources`                            | Crear un recurso                          |
| `GET`    | `/resources`                            | Listar recursos                           |
| `GET`    | `/resources/available`                  | Buscar recursos disponibles               |
| `GET`    | `/resources/{resource_id}/available-windows` | Consultar ventanas libres            |
| `GET`    | `/resources/{resource_id}`              | Consultar un recurso                      |
| `PATCH`  | `/resources/{resource_id}`              | Modificar parte de un recurso             |
| `DELETE` | `/resources/{resource_id}`              | Eliminar un recurso sin reservas          |
| `GET`    | `/resources/{resource_id}/availability` | Consultar disponibilidad entre dos fechas |

El listado se puede filtrar por `resource_type` e `is_active`. La búsqueda de recursos disponibles requiere `start_at` y `end_at`, y acepta los filtros opcionales `resource_type` y `min_capacity`; solamente devuelve recursos activos sin reservas superpuestas y usa la misma paginación que los demás listados.

Al crear o editar un recurso se pueden enviar `opening_time` y `closing_time` en formato `HH:MM:SS`. Deben enviarse juntas, usan UTC y definen una ventana diaria; las reservas y las consultas de disponibilidad deben quedar completamente dentro de ella. Si no se configuran, el recurso puede reservarse a cualquier hora. Esta primera versión no admite horarios que crucen la medianoche.

El campo `closed_dates` acepta una lista de fechas UTC con formato `YYYY-MM-DD`. Durante una fecha cerrada no se pueden crear o mover reservas, el recurso no aparece en las búsquedas de ese día y no se devuelven ventanas disponibles.

El campo `closed_weekdays` acepta los días semanales de cierre como números entre `0` (lunes) y `6` (domingo). Se aplica con las mismas reglas que `closed_dates`, por lo que sirve para configurar, por ejemplo, un recurso cerrado todos los domingos.

Tanto `/resources/available` como `/resources/{resource_id}/availability` aceptan `exclude_reservation_id`. Este parámetro permite comprobar un cambio de horario o buscar alternativas sin que la reserva que se está editando se compare consigo misma.

`/resources/{resource_id}/available-windows` devuelve los huecos continuos disponibles dentro de un rango de hasta siete días. `minimum_duration_minutes` permite descartar huecos demasiado cortos, con valores entre 30 y 480 minutos. También acepta `exclude_reservation_id`.

### Clientes

| Método   | Ruta                       | Para qué sirve                   |
| -------- | -------------------------- | -------------------------------- |
| `POST`   | `/customers`               | Crear un cliente                 |
| `GET`    | `/customers`               | Listar clientes                  |
| `GET`    | `/customers/{customer_id}` | Consultar un cliente             |
| `PATCH`  | `/customers/{customer_id}` | Modificar parte de un cliente    |
| `DELETE` | `/customers/{customer_id}` | Eliminar un cliente sin reservas |

El parámetro `search` permite buscar coincidencias en el nombre o en el email.

### Reservas

| Método  | Ruta                                    | Para qué sirve        |
| ------- | --------------------------------------- | --------------------- |
| `POST`  | `/reservations`                         | Crear una reserva     |
| `POST`  | `/reservations/recurring`               | Crear una serie semanal |
| `GET`   | `/reservations`                         | Listar reservas       |
| `GET`   | `/reservations/{reservation_id}`        | Consultar una reserva |
| `PATCH` | `/reservations/{reservation_id}`        | Modificar una reserva |
| `POST`  | `/reservations/{reservation_id}/cancel` | Cancelar una reserva  |

El listado acepta los filtros `resource_id`, `customer_id`, `series_id`, `status`, `start_date` y `end_date`. Las fechas se interpretan como días UTC y devuelven todas las reservas que se superponen con el rango, incluidas las que comienzan antes o terminan después. Si se envían ambas fechas, `start_date` no puede ser posterior a `end_date`.

Los tres listados usan `page` y `limit` para la paginación; el límite máximo es de 100 resultados por página. Los filtros se aplican antes de paginar y `total` indica la cantidad total de coincidencias.

`POST /reservations/recurring` recibe los mismos datos que una reserva normal, más `occurrences` (entre 2 y 52) e `interval_weeks` (por defecto, 1). La API valida toda la serie antes de crearla: si una ocurrencia no cumple las reglas de horario, cierre o disponibilidad, no se guarda ninguna. Cada reserva de la serie devuelve el mismo `series_id`.

`POST /reservations/{reservation_id}/cancel-series` cancela todas las reservas pendientes o confirmadas de la misma serie que todavía no hayan comenzado. Se puede usar el identificador de cualquiera de sus reservas; las ocurrencias pasadas y las ya finalizadas se conservan.

Una respuesta paginada tiene este formato:

```json
{
  "items": [],
  "page": 1,
  "limit": 20,
  "total": 0
}
```

## Cómo se manejan las fechas

Todas las fechas de una reserva deben incluir la zona horaria. Por ejemplo, una fecha de Argentina puede enviarse así:

```text
2026-08-01T10:00:00-03:00
```

La API convierte esa fecha a UTC antes de guardarla o compararla. Por eso la misma hora aparecerá en la respuesta de esta manera:

```text
2026-08-01T13:00:00Z
```

Las fechas sin zona horaria se rechazan. En esta etapa no hay una zona configurable para cada recurso o cliente.

## Reglas de las reservas

Una reserva debe cumplir estas condiciones:

- La fecha de inicio tiene que ser anterior a la fecha de finalización.
- No puede comenzar en el pasado.
- Debe durar como mínimo 30 minutos y como máximo 8 horas.
- El recurso tiene que estar activo.
- No puede cruzarse con otra reserva no cancelada del mismo recurso.

Los horarios pueden tocarse en los extremos. Por ejemplo, si una reserva termina a las 11:00, otra puede comenzar exactamente a las 11:00.

Cuando una reserva se cancela, conserva su registro pero deja de ocupar el horario. Si se cambia el recurso, la fecha de inicio o la fecha de finalización, la disponibilidad se comprueba otra vez sin comparar la reserva consigo misma.

Los estados siguen este recorrido sencillo:

```text
pending -> confirmed | cancelled
confirmed -> completed | cancelled
cancelled -> estado final
completed -> estado final
```

Una reserva nueva puede comenzar como `pending` o `confirmed`. Antes de confirmar una reserva pendiente, la API comprueba otra vez que el recurso esté activo, que el horario todavía no haya comenzado y que no existan conflictos. Una reserva confirmada sólo puede marcarse como `completed` después de su fecha de finalización. Las reservas canceladas o completadas son registros finales y ya no se pueden modificar.

Las reservas no tienen un endpoint de eliminación: se cancelan. Los recursos y clientes sí se pueden eliminar, siempre que no tengan ninguna reserva asociada.

## Respuestas de error

Los errores de negocio devuelven un código corto y un mensaje que explica el problema. Una superposición de horarios, por ejemplo, responde así:

```json
{
  "detail": {
    "code": "RESERVATION_CONFLICT",
    "message": "El recurso ya tiene una reserva que se superpone con el horario solicitado."
  }
}
```

También hay respuestas específicas para recursos, clientes o reservas inexistentes, emails repetidos, fechas incorrectas, recursos inactivos, eliminaciones no permitidas y cambios de estado inválidos. Los detalles internos de SQLAlchemy no se muestran al cliente.

## Cosas que todavía faltan

Esta versión está pensada para aprender y seguir creciendo, no para usarla directamente en producción. Algunas limitaciones actuales son:

- SQLite funciona bien para desarrollo y cargas pequeñas, pero no está pensado para mucha concurrencia.
- La validación de superposiciones se hace desde el servicio y todavía no tiene una protección transaccional fuerte frente a dos solicitudes simultáneas.
- Los endpoints son asíncronos, pero SQLAlchemy se está usando de forma síncrona.
- No hay login, usuarios, roles ni permisos.
- Las series recurrentes son semanales y no incluyen por ahora edición conjunta.
- Tampoco hay pagos, precios, notificaciones, recordatorios o lista de espera.
- El proyecto no incluye frontend, Docker ni configuración de despliegue.

## Ideas para continuar

Algunos pasos naturales para futuras versiones serían pasar a PostgreSQL, mejorar el control de concurrencia, agregar autenticación y sumar reglas como días no laborables y notificaciones.

Nada de eso forma parte de `v0.3.1`; por ahora el foco está en que la base sea clara, funcional y fácil de modificar.
