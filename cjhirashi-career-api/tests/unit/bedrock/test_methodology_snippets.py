"""Lectura selectiva de metodologías (spec 003, Bloque J — RF-016/017, RNF-005).

`search type=methodology` devuelve extractos; la lectura de UNA metodología entera
(`get_career_record` sobre `operational-methodologies`) usa un presupuesto propio.
Todo mockeado: sin Qdrant real, sin Bedrock (Art. 5).
"""
from unittest.mock import AsyncMock, patch

import pytest

from config import settings

_BIG_CONTENT = "Z" * 15000
# Forma real del `text` del payload (CareerRepository._record_to_text): el
# markdown va tras `content:`; title/section viajan como claves del payload.
_METH_TEXT = "content: # FASE 1\n" + _BIG_CONTENT


def _hit(**over):
    base = {
        "score": 0.91,
        "user_id": "usr-2",
        "type": "methodology",
        "resource_key": "operational-methodologies",
        "record_id": "opm-61",
        "text": _METH_TEXT,
        "title": "Redacción de Metodologías Operativas por Dominio",
        "section": "Soporte",
        "agent_profile_ids": ["agent_methodologies"],
    }
    base.update(over)
    return base


@pytest.mark.asyncio
@pytest.mark.requisito("RF-016")
async def test_search_methodology_returns_excerpts_not_full_text():
    from services import bedrock_service

    hits = [_hit()]
    with patch.object(bedrock_service, "embed_text", new=AsyncMock(return_value=[0.1])), patch(
        "services.qdrant_service.search", new=AsyncMock(return_value=hits)
    ):
        res = await bedrock_service._execute_tool(
            db=None,
            user_id="usr-2",
            name="search_knowledge_base",
            tool_input={"query": "redaccion metodologias", "type": "methodology"},
            session_id="s",
            caller_profile_id="agent_methodologies",
        )

    row = res["results"][0]
    assert row["record_id"] == "opm-61"
    assert row["title"].startswith("Redacción de Metodologías")
    assert row["section"] == "Soporte"
    assert "text" not in row  # NO el contenido completo
    assert "opm-61" in row["read_full"] and "get_career_record" in row["read_full"]
    assert "instruction" in res and "get_career_record" in res["instruction"]


@pytest.mark.asyncio
@pytest.mark.requisito("RNF-005")
async def test_methodology_excerpt_is_capped():
    from services import bedrock_service

    hits = [_hit(agent_profile_ids=[])]
    with patch.object(bedrock_service, "embed_text", new=AsyncMock(return_value=[0.1])), patch(
        "services.qdrant_service.search", new=AsyncMock(return_value=hits)
    ):
        res = await bedrock_service._execute_tool(
            None, "usr-2", "search_knowledge_base",
            {"query": "x", "type": "methodology"}, "s", caller_profile_id="agent_support",
        )
    assert len(res["results"][0]["excerpt"]) <= 800


@pytest.mark.asyncio
@pytest.mark.requisito("RF-016")
async def test_search_career_record_still_returns_raw_rows():
    """El cambio es SOLO para type=methodology."""
    from services import bedrock_service

    hits = [{"score": 0.5, "user_id": "usr-2", "type": "career_record",
             "resource_key": "competencies", "record_id": "cmp-1", "text": "algo"}]
    with patch.object(bedrock_service, "embed_text", new=AsyncMock(return_value=[0.1])), patch(
        "services.qdrant_service.search", new=AsyncMock(return_value=hits)
    ):
        res = await bedrock_service._execute_tool(
            None, "usr-2", "search_knowledge_base",
            {"query": "x", "type": "career_record"}, "s", caller_profile_id="agent_professional_identity",
        )
    assert res["results"][0]["text"] == "algo"


@pytest.mark.asyncio
@pytest.mark.requisito("RF-017")
async def test_get_methodology_not_truncated_under_budget():
    from services.bedrock import tools

    async def fake_exec(db, uid, name, ti, sid, caller_profile_id=None):
        return {"item": {"id": ti["record_id"], "content": _BIG_CONTENT, "title": "T", "section": "S"}}

    with patch.object(tools.bedrock_service, "_execute_tool", new=fake_exec):
        meth = await tools.execute_tool(
            None, "usr-2", "get_career_record",
            {"resource_key": "operational-methodologies", "record_id": "opm-61"}, "s",
        )
        proj = await tools.execute_tool(
            None, "usr-2", "get_career_record",
            {"resource_key": "projects", "record_id": "prj-1"}, "s",
        )

    # metodología: entera (cabe en 24k)
    assert meth["item"]["content"] == _BIG_CONTENT
    # projects: recortada por el tope global (8k)
    assert len(proj["item"]["content"]) < len(_BIG_CONTENT)


@pytest.mark.requisito("RF-017")
def test_methodology_budget_covers_largest_and_beats_global():
    assert settings.BEDROCK_MAX_METHODOLOGY_RESULT_CHARS >= 16000
    assert (
        settings.BEDROCK_MAX_METHODOLOGY_RESULT_CHARS
        > settings.BEDROCK_MAX_TOOL_RESULT_CHARS
    )
