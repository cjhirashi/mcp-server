"""Persistencia del override de tools por perfil (RF-001)."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.bedrock_agent_profile_tool import BedrockAgentProfileTool
from services.bedrock.agent_profiles import AGENT_PDF_DESIGN
from services.bedrock import profile_tools


@pytest.mark.asyncio
async def test_set_tool_override_upsert_update_and_delete():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(BedrockAgentProfileTool.__table__.create, checkfirst=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        # upsert: crea la fila
        state = await profile_tools.set_tool_override(db, AGENT_PDF_DESIGN, ["pdf_template"])
        assert state["override_tools"] == ["pdf_template"]
        assert "pdf_template" in state["effective_tools"]
        assert "delegate_to_specialist" in state["effective_tools"]  # L2 delega

        # update: reemplaza la fila existente
        state2 = await profile_tools.set_tool_override(db, AGENT_PDF_DESIGN, ["pdf_style"])
        assert state2["override_tools"] == ["pdf_style"]

        # delete: `None` restaura el default de código
        state3 = await profile_tools.set_tool_override(db, AGENT_PDF_DESIGN, None)
        assert state3["override_tools"] is None
        assert state3["effective_tools"] == state3["default_tools"]

    await engine.dispose()

