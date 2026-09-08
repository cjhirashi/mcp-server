"""Reindexado y consistencia del knowledge base de Agent Bedrock (spec 003).

El índice semántico (colección `career_knowledge` en Qdrant) quedó
desincronizado con Postgres tras una migración de IDs (usuario entero `2` ->
`"usr-2"`, record `33` -> `"opm-33"`) que nunca se re-corrió: `_point_id`
deriva de `resource_key:record_id`, así que los upserts nuevos no pisan los
viejos y la colección acumula dos generaciones de puntos. `qdrant_service.search`
filtra por `user_id` exacto, con lo que el agente solo ve la minoría de filas
re-escritas desde la migración.

`reindex_knowledge_base` reconstruye el índice desde Postgres (la fuente de
verdad) y purga los huérfanos. Es idempotente y se expone al operador vía
`POST /bedrock/knowledge-base/reindex`.
"""
import logging
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def _all_user_ids(db: AsyncSession) -> List[str]:
    from models.user import User

    result = await db.execute(select(User.id))
    return [uid for uid in result.scalars().all()]


async def reindex_knowledge_base(
    db: AsyncSession, user_id: Optional[str] = None
) -> Dict[str, object]:
    """(Re)indexa en Qdrant una entrada por fila viva de cada tabla
    vectorizable, y purga los puntos cuyo `user_id` ya no existe.

    `user_id=None` -> todos los usuarios. La purga SIEMPRE usa el conjunto
    completo de usuarios vigentes, no solo el alcance reindexado.

    Devuelve `{"reindexed": {<tipo>: n}, "purged_orphans": k, "users": u}`.
    """
    from repositories.career_repository import CareerRepository
    from routes.career_common import RESOURCE_REGISTRY, RESOURCE_VECTORIZE
    from services import qdrant_service

    all_user_ids = await _all_user_ids(db)
    targets = [user_id] if user_id is not None else list(all_user_ids)

    reindexed: Dict[str, int] = {}
    for resource_key, model in list(RESOURCE_REGISTRY.items()):
        vectorized = RESOURCE_VECTORIZE.get(resource_key, True)
        rtype = (
            "methodology"
            if resource_key == "operational-methodologies"
            else "career_record"
        )
        repo = CareerRepository(model, resource_key=resource_key, vectorize=True)
        for uid in targets:
            if vectorized:
                count = await repo.reindex_for_user(db, uid)
                if count:
                    reindexed[rtype] = reindexed.get(rtype, 0) + count
            else:
                # `vectorize=False` ahora, pero pudo estar indexado antes:
                # un rebuild verdadero deja 0 puntos para este recurso.
                await qdrant_service.prune_stale_points(uid, resource_key, [])

    purged = await qdrant_service.purge_orphans(all_user_ids)

    logger.info(
        "knowledge base reindexed: %s, orphans purged: %s, users: %s",
        reindexed,
        purged,
        len(targets),
    )
    return {"reindexed": reindexed, "purged_orphans": purged, "users": len(targets)}
