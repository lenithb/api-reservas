# Registro de cambios

Los cambios importantes del proyecto se documentan en este archivo. El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen [Semantic Versioning](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado

- Horarios diarios de apertura opcionales por recurso, aplicados al crear o mover reservas y al consultar disponibilidad.

## [0.3.1] - 2026-08-07

### Corregido

- La confirmación de una reserva pendiente vuelve a validar que el recurso esté activo, que el horario no haya comenzado y que siga libre de conflictos.

## [0.3.0] - 2026-08-07

### Agregado

- Búsqueda paginada de recursos disponibles por horario, tipo y capacidad mínima.
- Consultas de disponibilidad que pueden excluir la reserva que se está editando.
- Consulta de ventanas libres por recurso y duración mínima dentro de un rango de hasta siete días.

## [0.2.0] - 2026-08-07

### Agregado

- Paginación en los listados de recursos y clientes, con un límite máximo de 100 elementos por página.
- Esquema paginado común con los campos `items`, `page`, `limit` y `total`.
- Validaciones que impiden completar una reserva antes de su finalización o modificar reservas terminales.

### Cambiado

- Los listados de recursos y clientes ahora devuelven una respuesta paginada en lugar de un arreglo directo.
- Las reservas canceladas y completadas se consideran registros finales e inmutables.

### Corregido

- Los filtros de fecha incluyen las reservas que se superponen con el rango aunque comiencen antes o terminen después.
- Los filtros rechazan rangos donde `start_date` es posterior a `end_date`.

## [0.1.0] - 2026-07-28

### Agregado

- Primera versión de la API con recursos, clientes y reservas.
- Validación de disponibilidad y detección de horarios superpuestos.
- Cancelación de reservas y transiciones básicas de estado.
- Migraciones con Alembic, datos de ejemplo y pruebas automatizadas.

[Sin publicar]: https://github.com/lenithb/api-reservas/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/lenithb/api-reservas/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/lenithb/api-reservas/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/lenithb/api-reservas/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/lenithb/api-reservas/releases/tag/v0.1.0
