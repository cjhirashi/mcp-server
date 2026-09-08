"""
Qdrant service - Agent Bedrock's local knowledge base.

Single collection (`settings.QDRANT_COLLECTION`), one point per record from
any of the ~30 career-domain tables (including `operational_methodologies`),
keyed by a deterministic id derived from `{resource_key}:{record_id}` so
upserts/deletes are idempotent - callers never need to track Qdrant's own
point ids. Every point carries a `user_id` payload field for row-level
isolation, mirroring every SQL table in this project (see
`repositories/career_repository.py`, which calls this module after every
create/update/delete).

Kept deliberately dependency-free of the rest of the app (no FastAPI, no
SQLAlchemy) - just talks to Qdrant. Callers are responsible for treating
failures as best-effort (log and continue) rather than fatal, since a stale
search index should never block a real database write.
"""
import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import AsyncQdrantClient, models

from config import settings

_client: Optional[AsyncQdrantClient] = None


# ============================================================================
# Operaciones de colección
# ============================================================================

def _get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(url=settings.QDRANT_URL)
    return _client


def _point_id(resource_key: str, record_id: str) -> str:
    """Qdrant point ids must be a UUID or an unsigned int - derive a stable
    UUID from the natural key so re-indexing the same record is an upsert,
    never a duplicate."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"career_knowledge:{resource_key}:{record_id}"))


async def _collection_exists() -> bool:
    client = _get_client()
    collections = await client.get_collections()
    return any(c.name == settings.QDRANT_COLLECTION for c in collections.collections)


async def _ensure_collection(vector_size: int) -> None:
    if await _collection_exists():
        return
    client = _get_client()
    await client.create_collection(
        collection_name=settings.QDRANT_COLLECTION,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )


# ============================================================================
# Indexación
# ============================================================================

async def upsert_point(
    *,
    user_id: str,
    resource_type: str,
    resource_key: str,
    record_id: str,
    text: str,
    vector: List[float],
    extra_payload: Optional[Dict[str, Any]] = None,
    legacy_record_id: Optional[str] = None,
) -> None:
    """Index (or re-index) one record. `resource_type` is `"methodology"` or
    `"career_record"` - `operational_methodologies` goes through the same
    generic path as every other resource, since it's just another table
    behind `CareerRepository`.

    `legacy_record_id`: when the record's id was migrated from a bare integer
    to a prefixed form (`33` -> `opm-33`), the pre-migration point lives under
    a *different* `_point_id` and would otherwise linger forever. Passing the
    old id here deletes that twin right after the canonical upsert (spec 003
    RF-013). The full `reindex_knowledge_base` sweep is the backstop for
    twins this per-write cleanup can't reach."""
    await _ensure_collection(len(vector))
    client = _get_client()
    payload = {
        "user_id": user_id,
        "type": resource_type,
        "resource_key": resource_key,
        "record_id": record_id,
        "text": text,
    }
    if extra_payload:
        payload.update(extra_payload)
    canonical_id = _point_id(resource_key, record_id)
    await client.upsert(
        collection_name=settings.QDRANT_COLLECTION,
        points=[
            models.PointStruct(
                id=canonical_id,
                vector=vector,
                payload=payload,
            )
        ],
    )
    if legacy_record_id is not None and str(legacy_record_id) != str(record_id):
        legacy_id = _point_id(resource_key, str(legacy_record_id))
        if legacy_id != canonical_id:
            await client.delete(
                collection_name=settings.QDRANT_COLLECTION,
                points_selector=models.PointIdsList(points=[legacy_id]),
            )


async def prune_stale_points(user_id, resource_key: str, keep_record_ids) -> int:
    """Delete points for `(user_id, resource_key)` whose `record_id` is not in
    `keep_record_ids` - rows deleted from Postgres whose best-effort delete
    hook never reached Qdrant. Makes `reindex_knowledge_base` a true rebuild
    ("exactamente un punto por cada fila vigente", spec 003 RF-010). Returns
    the number of points removed."""
    if not await _collection_exists():
        return 0
    client = _get_client()
    keep = {str(r) for r in keep_record_ids}
    flt = models.Filter(
        must=[
            models.FieldCondition(key="user_id", match=models.MatchValue(value=str(user_id))),
            models.FieldCondition(key="resource_key", match=models.MatchValue(value=resource_key)),
        ]
    )
    doomed: List[Any] = []
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=settings.QDRANT_COLLECTION,
            scroll_filter=flt,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            if str((point.payload or {}).get("record_id")) not in keep:
                doomed.append(point.id)
        if offset is None:
            break
    for start in range(0, len(doomed), 500):
        await client.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=models.PointIdsList(points=doomed[start : start + 500]),
        )
    return len(doomed)


async def purge_orphans(valid_user_ids) -> int:
    """Delete every point whose payload `user_id` is not a current user id -
    leftovers from the integer->string user-id migration that `search` (which
    matches `user_id` exactly) can never return anyway (spec 003 RF-011).
    Returns the number of points removed. Idempotent: a second call finds
    nothing and returns 0."""
    if not await _collection_exists():
        return 0
    client = _get_client()
    valid = {str(u) for u in valid_user_ids}
    doomed: List[Any] = []
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=settings.QDRANT_COLLECTION,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            uid = (point.payload or {}).get("user_id")
            if str(uid) not in valid:
                doomed.append(point.id)
        if offset is None:
            break
    for start in range(0, len(doomed), 500):
        await client.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=models.PointIdsList(points=doomed[start : start + 500]),
        )
    return len(doomed)


async def delete_point(*, resource_key: str, record_id: str) -> None:
    client = _get_client()
    await client.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=models.PointIdsList(points=[_point_id(resource_key, record_id)]),
    )


async def set_point_payload(*, resource_key: str, record_id: str, payload: Dict[str, Any]) -> None:
    """Merge payload fields on an existing point without re-embedding.

    Missing points are ignored: the next CareerRepository write will upsert
    the full payload including `agent_profile_ids`.
    """
    if not await _collection_exists():
        return
    client = _get_client()
    try:
        await client.set_payload(
            collection_name=settings.QDRANT_COLLECTION,
            payload=payload,
            points=[_point_id(resource_key, record_id)],
        )
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if status == 404:
            return
        raise


# ============================================================================
# Búsqueda
# ============================================================================

async def search(
    *,
    user_id: str,
    vector: List[float],
    top_k: int = 5,
    resource_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Semantic search scoped to `user_id`, optionally filtered to
    `"methodology"` or `"career_record"`. Returns `[]` if nothing has been
    indexed yet rather than erroring - an empty knowledge base is a valid
    state, not a failure."""
    if not await _collection_exists():
        return []
    client = _get_client()
    must = [models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
    if resource_type:
        must.append(models.FieldCondition(key="type", match=models.MatchValue(value=resource_type)))
    result = await client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=vector,
        query_filter=models.Filter(must=must),
        limit=top_k,
    )
    return [{"score": point.score, **point.payload} for point in result.points]


async def scroll_points(
    *,
    user_id: str,
    resource_type: Optional[str] = None,
    extra_must: Optional[Dict[str, Any]] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Lista puntos por payload (sin vector). Vacío si la colección no existe."""
    if not await _collection_exists():
        return []
    client = _get_client()
    must = [models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
    if resource_type:
        must.append(models.FieldCondition(key="type", match=models.MatchValue(value=resource_type)))
    for key, value in (extra_must or {}).items():
        must.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
    points, _ = await client.scroll(
        collection_name=settings.QDRANT_COLLECTION,
        scroll_filter=models.Filter(must=must),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return [dict(point.payload or {}) for point in points]
