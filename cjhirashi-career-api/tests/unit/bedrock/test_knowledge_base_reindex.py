"""Reindexado del knowledge base (spec 003, reapertura — RF-010/011/012/015, RNF-003/004).

Todo mockeado: sin Qdrant real, sin llamadas a Bedrock (Art. 5).
"""
from unittest.mock import AsyncMock, patch

import pytest

# Importar la app puebla RESOURCE_REGISTRY (cada router se registra al construirse).
from app import app  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.requisito("RF-010")
async def test_reindex_upserts_one_point_per_row():
    from services.bedrock import knowledge_base as kb

    seen = []

    async def fake_reindex_for_user(self, db, uid):
        table = {
            ("operational-methodologies", "usr-2"): 3,
            ("operational-methodologies", "usr-1"): 1,
            ("competencies", "usr-2"): 5,
        }
        n = table.get((self.resource_key, uid), 0)
        seen.append((self.resource_key, uid, n))
        return n

    with patch(
        "services.bedrock.knowledge_base._all_user_ids",
        new=AsyncMock(return_value=["usr-1", "usr-2"]),
    ), patch(
        "repositories.career_repository.CareerRepository.reindex_for_user",
        new=fake_reindex_for_user,
    ), patch(
        "services.qdrant_service.purge_orphans", new=AsyncMock(return_value=7)
    ) as purge, patch(
        "services.qdrant_service.prune_stale_points", new=AsyncMock(return_value=0)
    ):
        result = await kb.reindex_knowledge_base(db=None, user_id=None)

    assert result["users"] == 2
    assert result["purged_orphans"] == 7
    assert result["reindexed"].get("methodology") == 4
    assert result["reindexed"].get("career_record") == 5
    # La purga recibe el conjunto COMPLETO de usuarios vigentes.
    purge.assert_awaited_once()
    assert set(purge.await_args.args[0]) == {"usr-1", "usr-2"}


@pytest.mark.asyncio
@pytest.mark.requisito("RF-010")
async def test_reindex_prunes_non_vectorized_resources_to_empty():
    """Un recurso `vectorize=False` (p.ej. cv-versions) que estuvo indexado antes
    debe quedar en 0 puntos tras el rebuild."""
    from services.bedrock import knowledge_base as kb

    async def fake_reindex_for_user(self, db, uid):
        return 0

    prune_calls = []

    async def fake_prune(uid, rkey, keep):
        prune_calls.append((uid, rkey, list(keep)))
        return 0

    with patch(
        "services.bedrock.knowledge_base._all_user_ids",
        new=AsyncMock(return_value=["usr-2"]),
    ), patch(
        "repositories.career_repository.CareerRepository.reindex_for_user",
        new=fake_reindex_for_user,
    ), patch(
        "services.qdrant_service.purge_orphans", new=AsyncMock(return_value=0)
    ), patch("services.qdrant_service.prune_stale_points", new=fake_prune):
        await kb.reindex_knowledge_base(db=None, user_id=None)

    # cv-versions / pdf-* -> prune con keep vacío
    non_vec = {rkey for _, rkey, keep in prune_calls if keep == []}
    assert "cv-versions" in non_vec
    assert "pdf-output-templates" in non_vec


@pytest.mark.asyncio
@pytest.mark.requisito("RF-012")
async def test_reindex_scoped_to_single_user():
    from services.bedrock import knowledge_base as kb

    async def fake_reindex_for_user(self, db, uid):
        assert uid == "usr-2"
        return 2 if self.resource_key == "operational-methodologies" else 0

    with patch(
        "services.bedrock.knowledge_base._all_user_ids",
        new=AsyncMock(return_value=["usr-1", "usr-2"]),
    ), patch(
        "repositories.career_repository.CareerRepository.reindex_for_user",
        new=fake_reindex_for_user,
    ), patch(
        "services.qdrant_service.purge_orphans", new=AsyncMock(return_value=0)
    ) as purge, patch(
        "services.qdrant_service.prune_stale_points", new=AsyncMock(return_value=0)
    ):
        result = await kb.reindex_knowledge_base(db=None, user_id="usr-2")

    assert result["users"] == 1
    assert result["reindexed"].get("methodology") == 2
    # Aun con alcance de un usuario, la purga usa todos los usuarios vigentes.
    assert set(purge.await_args.args[0]) == {"usr-1", "usr-2"}


@pytest.mark.asyncio
@pytest.mark.requisito("RNF-003")
async def test_reindex_is_idempotent():
    from services.bedrock import knowledge_base as kb

    async def fake_reindex_for_user(self, db, uid):
        return 3 if self.resource_key == "operational-methodologies" else 0

    purge_returns = iter([9, 0])

    async def fake_purge(valid):
        return next(purge_returns)

    with patch(
        "services.bedrock.knowledge_base._all_user_ids",
        new=AsyncMock(return_value=["usr-2"]),
    ), patch(
        "repositories.career_repository.CareerRepository.reindex_for_user",
        new=fake_reindex_for_user,
    ), patch("services.qdrant_service.purge_orphans", new=fake_purge), patch(
        "services.qdrant_service.prune_stale_points", new=AsyncMock(return_value=0)
    ):
        first = await kb.reindex_knowledge_base(db=None, user_id=None)
        second = await kb.reindex_knowledge_base(db=None, user_id=None)

    assert first["reindexed"] == second["reindexed"]
    assert first["purged_orphans"] == 9
    assert second["purged_orphans"] == 0


@pytest.mark.asyncio
@pytest.mark.requisito("RNF-004")
async def test_reindex_for_user_pages_rows_in_batches():
    from repositories.career_repository import CareerRepository
    from models.operational_methodology import OperationalMethodology

    repo = CareerRepository(
        OperationalMethodology, resource_key="operational-methodologies", vectorize=True
    )

    class _Row:
        def __init__(self, rid):
            self.id = rid

    pages = [
        [_Row(f"opm-{i}") for i in range(100)],
        [_Row(f"opm-{i}") for i in range(100, 150)],
        [],
    ]
    list_calls = []

    async def fake_list_for_user(db, user_id, skip=0, limit=20, **kw):
        list_calls.append((skip, limit))
        idx = skip // 100
        return pages[idx] if idx < len(pages) else []

    indexed = []

    async def fake_index(obj, uid):
        indexed.append(obj.id)

    prune_spy = AsyncMock(return_value=0)
    with patch.object(repo, "list_for_user", new=fake_list_for_user), patch.object(
        repo, "_index_for_search", new=fake_index
    ), patch("services.qdrant_service.prune_stale_points", new=prune_spy):
        n = await repo.reindex_for_user(db=None, user_id="usr-2")

    assert n == 150
    assert len(indexed) == 150
    # Paginó: al menos 2 llamadas de página, nunca un solo select de toda la tabla.
    assert len(list_calls) >= 2
    assert all(limit == 100 for _, limit in list_calls)
    # Poda de rebuild: recibe los 150 ids vivos para (usr-2, operational-methodologies).
    prune_spy.assert_awaited_once()
    assert prune_spy.await_args.args[0] == "usr-2"
    assert prune_spy.await_args.args[1] == "operational-methodologies"
    assert len(prune_spy.await_args.args[2]) == 150


@pytest.mark.asyncio
@pytest.mark.requisito("RF-010")
async def test_reindex_for_user_noop_without_resource_key_or_vectorize():
    from repositories.career_repository import CareerRepository
    from models.operational_methodology import OperationalMethodology

    no_key = CareerRepository(OperationalMethodology)
    assert await no_key.reindex_for_user(db=None, user_id="usr-2") == 0

    not_vec = CareerRepository(
        OperationalMethodology, resource_key="operational-methodologies", vectorize=False
    )
    assert await not_vec.reindex_for_user(db=None, user_id="usr-2") == 0


@pytest.mark.asyncio
@pytest.mark.requisito("RF-010")
async def test_reindex_for_user_empty_table_returns_zero():
    from unittest.mock import patch

    from repositories.career_repository import CareerRepository
    from models.operational_methodology import OperationalMethodology

    repo = CareerRepository(
        OperationalMethodology, resource_key="operational-methodologies", vectorize=True
    )

    async def empty_list(db, user_id, skip=0, limit=20, **kw):
        return []

    with patch.object(repo, "list_for_user", new=empty_list), patch(
        "services.qdrant_service.prune_stale_points", new=AsyncMock(return_value=0)
    ):
        assert await repo.reindex_for_user(db=None, user_id="usr-2") == 0


def test_legacy_record_id_none_when_resource_has_no_prefix():
    from repositories.career_repository import CareerRepository
    from models.operational_methodology import OperationalMethodology

    repo = CareerRepository(OperationalMethodology, resource_key="not-a-real-resource")
    assert repo._legacy_record_id("whatever-1") is None


@pytest.mark.asyncio
@pytest.mark.requisito("RF-012")
async def test_all_user_ids_reads_users_table():
    from services.bedrock import knowledge_base as kb

    class _Scalars:
        def all(self):
            return ["usr-1", "usr-2"]

    class _Result:
        def scalars(self):
            return _Scalars()

    class _DB:
        async def execute(self, *a, **k):
            return _Result()

    assert await kb._all_user_ids(_DB()) == ["usr-1", "usr-2"]


@pytest.mark.asyncio
@pytest.mark.requisito("RF-015")
async def test_search_methodology_returns_assigned_only_after_reindex():
    """Tras reindexar, search(type=methodology) + applies_to_agent devuelve solo lo
    asignado al perfil consultante. Qdrant simulado con una lista de payloads."""
    from services import qdrant_service
    from services.methodology_scope import applies_to_agent

    store = [
        {
            "user_id": "usr-2",
            "type": "methodology",
            "record_id": "opm-29",
            "text": "Proceso 5 - Portafolio",
            "agent_profile_ids": ["agent_professional_identity"],
        },
        {
            "user_id": "usr-2",
            "type": "methodology",
            "record_id": "opm-57",
            "text": "WeasyPrint",
            "agent_profile_ids": ["agent_pdf_design", "agent_pdf_render"],
        },
        {
            "user_id": "usr-2",
            "type": "methodology",
            "record_id": "opm-37",
            "text": "Mapa de relaciones",
            "agent_profile_ids": [],
        },
    ]

    async def fake_search(*, user_id, vector, top_k=5, resource_type=None):
        return [
            {"score": 1.0, **row}
            for row in store
            if row["user_id"] == user_id
            and (resource_type is None or row["type"] == resource_type)
        ]

    with patch.object(qdrant_service, "search", new=fake_search):
        rows = await qdrant_service.search(
            user_id="usr-2", vector=[0.1], resource_type="methodology"
        )
    visible = [
        r for r in rows if applies_to_agent(r.get("agent_profile_ids"), "agent_professional_identity")
    ]
    ids = {r["record_id"] for r in visible}
    assert ids == {"opm-29", "opm-37"}  # asignada + compartida, nunca la de pdf
