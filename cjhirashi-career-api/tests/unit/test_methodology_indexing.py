"""RF-007: el payload de Qdrant para metodologías lleva agent_profile_ids."""
from unittest.mock import AsyncMock, patch

import pytest

from models.operational_methodology import OperationalMethodology
from repositories.career_repository import CareerRepository


@pytest.mark.asyncio
async def test_index_for_search_includes_agent_profile_ids_for_methodology():
    repo = CareerRepository(
        OperationalMethodology,
        resource_key="operational-methodologies",
        vectorize=True,
    )
    obj = OperationalMethodology(
        id="opm-1",
        user_id="usr-1",
        title="Metodología X",
        content="# contenido",
        agent_profile_ids=["agent_pdf_design"],
    )
    with patch(
        "services.bedrock_service.embed_text", new=AsyncMock(return_value=[0.1, 0.2])
    ), patch("services.qdrant_service.upsert_point", new=AsyncMock()) as upsert:
        await repo._index_for_search(obj, "usr-1")
        upsert.assert_awaited_once()
        kwargs = upsert.call_args.kwargs
        assert kwargs["resource_type"] == "methodology"
        assert kwargs["extra_payload"] == {"agent_profile_ids": ["agent_pdf_design"]}
