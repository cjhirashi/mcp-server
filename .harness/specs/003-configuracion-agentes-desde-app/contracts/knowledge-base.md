# Contrato — Reindexado del knowledge base

Feature 003 (reapertura 2026-09-07). Referencia humana; el gate no ancla OpenAPI todavía.

## POST `/bedrock/knowledge-base/reindex`

Reconstruye el índice semántico de Agent Bedrock (`career_knowledge` en Qdrant) para
**todos** los usuarios y purga los puntos huérfanos dejados por la migración de IDs.
Operación de mantenimiento del operador. **Síncrona**: responde cuando termina.

- Auth: `get_current_user` (cualquier usuario autenticado).
- Sin body.
- Coste: 1 llamada de embedding (Titan) por fila vectorizable. Decenas de segundos hoy.

Respuesta `200`:

```json
{
  "reindexed": { "methodology": 23, "career_record": 338 },
  "purged_orphans": 250,
  "users": 2
}
```

- `reindexed` — puntos upserted por `type` de payload (`methodology` = tabla
  `operational_methodologies`; `career_record` = el resto de tablas con `vectorize=True`).
- `purged_orphans` — puntos borrados cuyo `user_id` de payload no era un usuario vigente.
- `users` — usuarios alcanzados por el reindexado.

Errores (RFC 9457):

- `503` — Qdrant no disponible (o cae a media corrida). `detail` indica hasta qué
  `resource_key` se llegó; el resto queda sin reindexar (re-ejecutable: la operación es
  idempotente).

## Idempotencia

Dos `POST` seguidos sin escrituras intermedias: el segundo devuelve los mismos
`reindexed` y `purged_orphans: 0` (mismo `_point_id` por registro; ya no quedan
huérfanos).

## Script operativo (no es endpoint)

`python scripts/check_kb_consistency.py` — compara, por `type` y usuario, conteo de
puntos Qdrant vigentes vs filas PG. Solo imprime divergencias y huérfanos; no modifica
nada. Correr post-deploy y tras cualquier migración de IDs.
