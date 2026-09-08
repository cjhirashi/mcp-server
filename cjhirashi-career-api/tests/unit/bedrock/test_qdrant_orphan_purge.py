"""Purga del gemelo heredado en el upsert (spec 003, reapertura — RF-013).

Cuando un record migró de id entero (`33`) a prefijado (`opm-33`), el punto
viejo vive bajo otro `_point_id` y quedaría huérfano para siempre. El upsert
canónico debe borrarlo en el mismo paso.
"""
from unittest.mock import AsyncMock, patch

import pytest

from models.operational_methodology import OperationalMethodology
from repositories.career_repository import CareerRepository
from services import qdrant_service


def _repo():
    return CareerRepository(
        OperationalMethodology,
        resource_key="operational-methodologies",
        vectorize=True,
    )


@pytest.mark.asyncio
@pytest.mark.requisito("RF-013")
async def test_index_for_search_passes_legacy_id_and_deletes_twin():
    repo = _repo()
    obj = OperationalMethodology(
        id="opm-33",
        user_id="usr-2",
        title="Proceso X",
        content="# contenido",
        agent_profile_ids=["agent_pdf_design"],
    )

    fake_client = AsyncMock()
    with patch(
        "services.bedrock_service.embed_text", new=AsyncMock(return_value=[0.1, 0.2])
    ), patch("services.qdrant_service._ensure_collection", new=AsyncMock()), patch(
        "services.qdrant_service._get_client", return_value=fake_client
    ):
        await repo._index_for_search(obj, "usr-2")

    # upsert canónico con el id prefijado
    fake_client.upsert.assert_awaited_once()
    up_kwargs = fake_client.upsert.await_args.kwargs
    assert up_kwargs["points"][0].id == qdrant_service._point_id(
        "operational-methodologies", "opm-33"
    )
    # delete del gemelo heredado (id sin prefijo: "33")
    fake_client.delete.assert_awaited_once()
    del_kwargs = fake_client.delete.await_args.kwargs
    assert del_kwargs["points_selector"].points == [
        qdrant_service._point_id("operational-methodologies", "33")
    ]


@pytest.mark.asyncio
@pytest.mark.requisito("RF-013")
async def test_no_twin_delete_when_id_has_no_numeric_suffix():
    repo = _repo()
    obj = OperationalMethodology(
        id="opm-weird",  # no es {prefix}-{int}
        user_id="usr-2",
        title="Proceso Y",
        content="# c",
        agent_profile_ids=[],
    )
    fake_client = AsyncMock()
    with patch(
        "services.bedrock_service.embed_text", new=AsyncMock(return_value=[0.1, 0.2])
    ), patch("services.qdrant_service._ensure_collection", new=AsyncMock()), patch(
        "services.qdrant_service._get_client", return_value=fake_client
    ):
        await repo._index_for_search(obj, "usr-2")

    fake_client.upsert.assert_awaited_once()
    fake_client.delete.assert_not_awaited()


def test_legacy_record_id_derivation():
    repo = _repo()
    assert repo._legacy_record_id("opm-33") == "33"
    assert repo._legacy_record_id("opm-7") == "7"
    assert repo._legacy_record_id("opm-weird") is None
    assert repo._legacy_record_id("33") is None
    assert repo._legacy_record_id(33) is None


@pytest.mark.asyncio
@pytest.mark.requisito("RF-011")
async def test_purge_orphans_deletes_only_non_current_users():
    class _P:
        def __init__(self, pid, uid):
            self.id = pid
            self.payload = {"user_id": uid}

    # dos páginas de scroll; la 2ª cierra con offset None
    pages = [
        ([_P("a", "usr-2"), _P("b", 2), _P("c", "usr-1")], "next"),
        ([_P("d", "3"), _P("e", "usr-2")], None),
    ]
    calls = iter(pages)
    deleted = []

    class _Client:
        async def scroll(self, **kw):
            return next(calls)

        async def delete(self, *, collection_name, points_selector):
            deleted.extend(points_selector.points)

    with patch("services.qdrant_service._collection_exists", new=AsyncMock(return_value=True)), patch(
        "services.qdrant_service._get_client", return_value=_Client()
    ):
        n = await qdrant_service.purge_orphans({"usr-1", "usr-2"})

    assert n == 2
    assert set(deleted) == {"b", "d"}  # user_id 2 y "3" no son usuarios vigentes


@pytest.mark.asyncio
@pytest.mark.requisito("RF-011")
async def test_purge_orphans_noop_when_collection_missing():
    with patch(
        "services.qdrant_service._collection_exists", new=AsyncMock(return_value=False)
    ):
        assert await qdrant_service.purge_orphans({"usr-1"}) == 0


@pytest.mark.asyncio
@pytest.mark.requisito("RF-010")
async def test_prune_stale_points_removes_rows_not_in_keep_set():
    """RF-010 ('exactamente un punto por fila vigente'): un punto de un record
    borrado de Postgres — mismo user_id, no huérfano — se elimina."""

    class _P:
        def __init__(self, pid, rid):
            self.id = pid
            self.payload = {"user_id": "usr-2", "resource_key": "competencies", "record_id": rid}

    pages = [([_P("p1", "cmp-1"), _P("p2", "cmp-999"), _P("p3", "cmp-2")], None)]
    calls = iter(pages)
    deleted = []

    class _Client:
        async def scroll(self, **kw):
            return next(calls)

        async def delete(self, *, collection_name, points_selector):
            deleted.extend(points_selector.points)

    with patch(
        "services.qdrant_service._collection_exists", new=AsyncMock(return_value=True)
    ), patch("services.qdrant_service._get_client", return_value=_Client()):
        n = await qdrant_service.prune_stale_points(
            "usr-2", "competencies", ["cmp-1", "cmp-2"]
        )

    assert n == 1
    assert deleted == ["p2"]  # cmp-999 ya no existe en PG


@pytest.mark.asyncio
@pytest.mark.requisito("RF-010")
async def test_prune_stale_points_noop_when_collection_missing():
    with patch(
        "services.qdrant_service._collection_exists", new=AsyncMock(return_value=False)
    ):
        assert await qdrant_service.prune_stale_points("usr-2", "competencies", []) == 0
