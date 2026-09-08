"""Alcance de metodologías a agentes y validación de agent_profile_ids."""
import pytest
from pydantic import ValidationError

from services.methodology_scope import applies_to_agent
from services.bedrock.agent_profiles import AGENT_METHODOLOGIES, AGENT_PDF_DESIGN, known_agent_profile_ids
from schemas.career_methodologies import OperationalMethodologyCreate


def test_applies_to_all_when_empty():
    assert applies_to_agent(None, AGENT_PDF_DESIGN)
    assert applies_to_agent([], AGENT_PDF_DESIGN)


def test_applies_only_to_listed_agents():
    ids = [AGENT_PDF_DESIGN]
    assert applies_to_agent(ids, AGENT_PDF_DESIGN)
    assert not applies_to_agent(ids, "agent_search_operations")


def test_methodologies_guardian_sees_all():
    assert applies_to_agent(["agent_pdf_design"], AGENT_METHODOLOGIES)


def test_known_agent_ids_include_web_and_github():
    known = known_agent_profile_ids()
    assert "agent_web_search" in known
    assert "agent_github" in known


def test_schema_accepts_known_ids():
    row = OperationalMethodologyCreate(
        title="Diseño PDF",
        content="# h",
        agent_profile_ids=["agent_pdf_design", "agent_pdf_render"],
    )
    assert row.agent_profile_ids == ["agent_pdf_design", "agent_pdf_render"]


def test_schema_rejects_unknown_ids():
    with pytest.raises(ValidationError):
        OperationalMethodologyCreate(
            title="X",
            content="# h",
            agent_profile_ids=["not_an_agent"],
        )


def test_is_shared_when_empty():
    from services.methodology_scope import is_shared_methodology

    assert is_shared_methodology(None)
    assert is_shared_methodology([])
    assert not is_shared_methodology(["agent_pdf_design"])


def test_next_ids_assign_appends_to_exclusive_list():
    from services.methodology_scope import next_agent_profile_ids

    known = known_agent_profile_ids()
    nxt = next_agent_profile_ids(["agent_search_operations"], AGENT_PDF_DESIGN, True, known)
    assert nxt == ["agent_search_operations", AGENT_PDF_DESIGN]


def test_next_ids_unassign_shared_expands_to_everyone_else():
    from services.methodology_scope import next_agent_profile_ids

    known = known_agent_profile_ids()
    nxt = next_agent_profile_ids([], AGENT_PDF_DESIGN, False, known)
    assert AGENT_PDF_DESIGN not in nxt
    assert AGENT_METHODOLOGIES in nxt
    assert set(nxt) == known - {AGENT_PDF_DESIGN}


def test_next_ids_unassign_last_owner_parks_with_guardian():
    from services.methodology_scope import next_agent_profile_ids

    nxt = next_agent_profile_ids(
        [AGENT_PDF_DESIGN], AGENT_PDF_DESIGN, False, known_agent_profile_ids()
    )
    assert nxt == [AGENT_METHODOLOGIES]


def test_next_ids_noop_when_already_shared_and_assigning():
    from services.methodology_scope import next_agent_profile_ids

    assert next_agent_profile_ids([], AGENT_PDF_DESIGN, True, known_agent_profile_ids()) is None


@pytest.mark.asyncio
@pytest.mark.requisito("RF-014")
async def test_set_agent_methodologies_forces_reindex_without_net_change():
    """RF-014: guardar la asignación reindexa TODAS las metodologías del
    usuario en Qdrant aunque `agent_profile_ids` no cambie para ninguna."""
    from unittest.mock import AsyncMock, patch

    from services import methodology_scope as ms

    class _Meth:
        def __init__(self, mid):
            self.id = mid
            self.title = f"Metodología {mid}"
            self.section = "X"
            self.agent_profile_ids = []  # compartida

    rows = [_Meth("opm-1"), _Meth("opm-2")]

    class _Result:
        def scalars(self):
            class _S:
                def all(_self):
                    return rows

            return _S()

        def all(self):
            return rows

    class _DB:
        async def execute(self, *a, **k):
            return _Result()

    reindex_spy = AsyncMock(return_value=2)
    update_spy = AsyncMock()

    with patch(
        "repositories.career_repository.CareerRepository.reindex_for_user", new=reindex_spy
    ), patch(
        "repositories.career_repository.CareerRepository.update_for_user", new=update_spy
    ):
        # wanted == todos los ids -> next_agent_profile_ids devuelve None para todos
        await ms.set_agent_methodologies(_DB(), "usr-2", AGENT_PDF_DESIGN, ["opm-1", "opm-2"])

    update_spy.assert_not_awaited()          # ninguna asignación cambió
    reindex_spy.assert_awaited_once()        # ...pero igual se reindexó
    assert reindex_spy.await_args.args[1:] == ("usr-2",)
