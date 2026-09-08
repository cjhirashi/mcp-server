"""Comprueba la consistencia del knowledge base de Agent Bedrock (spec 003).

Compara, por tipo de recurso y por usuario, el número de puntos VIGENTES en
la colección Qdrant `career_knowledge` (payload `user_id` = un usuario real)
contra el número de filas en Postgres de las tablas vectorizables. Además
cuenta los puntos HUÉRFANOS (payload `user_id` que ya no existe — restos de
la migración de IDs enteros → prefijados).

**Solo lee. No modifica nada.** Para sanear, usa el endpoint
`POST /bedrock/knowledge-base/reindex` (o `reindex_knowledge_base` en un
shell). Correr este script:

  - después de cada despliegue,
  - después de cualquier migración que cambie ids o `user_id`,
  - si el agente reporta que "no encuentra" metodologías o registros.

Cómo correrlo (dentro del contenedor api, con acceso a Postgres y Qdrant):

    docker cp cjhirashi-career-api/scripts/check_kb_consistency.py \
        cjhirashi-career-api:/app/scripts/check_kb_consistency.py
    docker exec -w /app/src cjhirashi-career-api python \
        /app/scripts/check_kb_consistency.py

Sale con código 0 si Qdrant y Postgres cuadran y no hay huérfanos; 1 si hay
divergencias o huérfanos (para encadenarlo en un check de post-deploy).
"""
import asyncio
import logging
import sys
from collections import defaultdict

sys.path.insert(0, "/app/src")
sys.path.insert(0, "src")

# El engine puede venir con echo=True (DEBUG); este script solo reporta.
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


async def main() -> int:
    from sqlalchemy import func, select

    from app import app  # noqa: F401  -> puebla RESOURCE_REGISTRY

    # El engine se crea con echo=True bajo DEBUG y sube el logger a INFO; este
    # script solo reporta, así que lo bajamos DESPUÉS de importar.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    from database import AsyncSessionLocal
    from models.user import User
    from repositories.career_repository import CareerRepository
    from routes.career_common import RESOURCE_REGISTRY, RESOURCE_VECTORIZE
    from services import qdrant_service

    async with AsyncSessionLocal() as db:
        user_ids = [u for u in (await db.execute(select(User.id))).scalars().all()]
        valid = set(user_ids)

        # --- Postgres: filas por (type, user) ---
        pg_counts: dict = defaultdict(lambda: defaultdict(int))
        for resource_key, model in RESOURCE_REGISTRY.items():
            if not RESOURCE_VECTORIZE.get(resource_key, True):
                continue
            rtype = "methodology" if resource_key == "operational-methodologies" else "career_record"
            for uid in user_ids:
                n = (
                    await db.execute(
                        select(func.count()).select_from(model).where(model.user_id == uid)
                    )
                ).scalar_one()
                pg_counts[rtype][uid] += n

        # --- Qdrant: puntos por (type, user) + huérfanos ---
        client = qdrant_service._get_client()
        qd_counts: dict = defaultdict(lambda: defaultdict(int))
        orphans = 0
        offset = None
        while True:
            points, offset = await client.scroll(
                collection_name=qdrant_service.settings.QDRANT_COLLECTION,
                limit=500,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                pl = p.payload or {}
                uid = str(pl.get("user_id"))
                if uid not in valid:
                    orphans += 1
                    continue
                qd_counts[pl.get("type") or "career_record"][uid] += 1
            if offset is None:
                break

    # --- Reporte ---
    ok = True
    print("=== Consistencia knowledge base (Qdrant vs Postgres) ===")
    for rtype in sorted(set(pg_counts) | set(qd_counts)):
        for uid in sorted(set(pg_counts[rtype]) | set(qd_counts[rtype])):
            pg = pg_counts[rtype][uid]
            qd = qd_counts[rtype][uid]
            flag = "" if pg == qd else "  <-- DIVERGE"
            if pg != qd:
                ok = False
            print(f"  {rtype:14} {uid:10} PG={pg:5} Qdrant={qd:5}{flag}")
    print(f"\nHuérfanos (user_id no vigente): {orphans}")
    if orphans:
        ok = False

    if ok:
        print("\nOK: cuadran y sin huérfanos.")
        return 0
    print("\nINCONSISTENTE: corre POST /bedrock/knowledge-base/reindex.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
