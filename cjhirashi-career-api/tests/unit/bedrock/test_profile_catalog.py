"""Catálogo de agentes: definición de código y tools resueltas."""
from services.bedrock.agent_profiles import (
    AGENT_ORCHESTRATOR,
    AGENT_PDF_DESIGN,
    AGENT_PDF_RENDER,
    AGENT_PROFESSIONAL_IDENTITY,
    get_profile,
    list_profiles,
)
from services.bedrock.profile_catalog import resolved_tool_names, _serialize_definition


def test_get_profile_accepts_catalog_record_id():
    from services.bedrock.agent_profiles import agent_record_id

    assert get_profile("agent-1").id == AGENT_ORCHESTRATOR
    assert get_profile(AGENT_ORCHESTRATOR).id == AGENT_ORCHESTRATOR
    profiles = list_profiles()
    assert len(profiles) >= 18
    record_ids = {agent_record_id(p.id) for p in profiles}
    assert len(record_ids) == len(profiles)
    assert all(item.startswith("agent-") for item in record_ids)


def test_orchestrator_tools_are_delegate_only():
    tools = resolved_tool_names(get_profile(AGENT_ORCHESTRATOR))
    assert tools == ["delegate_to_specialist"]


def test_identity_has_career_crud_and_search():
    tools = resolved_tool_names(get_profile(AGENT_PROFESSIONAL_IDENTITY))
    assert "list_career_record" in tools
    assert "search_knowledge_base" in tools
    assert "delegate_to_specialist" in tools
    assert "generate_pdf" not in tools


def test_pdf_render_has_no_own_memory_or_tables():
    profile = get_profile(AGENT_PDF_RENDER)
    meta = {
        "default_suffix": profile.system_prompt_suffix,
        "override_suffix": None,
        "effective_suffix": profile.system_prompt_suffix,
        "is_default": True,
    }
    item = _serialize_definition(profile, meta)
    assert item["id"] == "agent-9"
    assert item["photo_url"] is None
    assert item["system_name"] == AGENT_PDF_RENDER
    assert item["profile_id"] == AGENT_PDF_RENDER
    assert item["has_own_memory"] is False
    assert item["user_facing"] is False
    assert "generate_pdf" in item["tools"]
    assert item["prompt_is_default"] is True


def test_pdf_design_lists_template_tables():
    profile = get_profile(AGENT_PDF_DESIGN)
    meta = {
        "default_suffix": "x",
        "override_suffix": "custom",
        "effective_suffix": "custom",
        "is_default": False,
    }
    item = _serialize_definition(profile, meta, "https://files.example/agent.png")
    assert item["photo_url"] == "https://files.example/agent.png"
    assert item["system_name"] == AGENT_PDF_DESIGN
    assert "pdf-output-templates" in item["resource_keys"]
    assert "pdf-template-styles" in item["resource_keys"]
    assert item["prompt_is_default"] is False
    assert item["has_own_memory"] is True
    assert item["sections"] == []


def test_serialize_definition_exposes_tool_state():
    profile = get_profile(AGENT_PDF_DESIGN)
    meta = {
        "default_suffix": "x",
        "override_suffix": None,
        "effective_suffix": "x",
        "is_default": True,
    }
    item = _serialize_definition(profile, meta)
    assert item["override_tools"] is None
    assert item["effective_tools"] == item["default_tools"]
    assert item["tools"] == item["effective_tools"]

    override = ["pdf_template", "pdf_style"]
    item2 = _serialize_definition(profile, meta, None, override)
    assert item2["override_tools"] == sorted(override)
    assert "delegate_to_specialist" in item2["effective_tools"]
    assert item2["tools"] == item2["effective_tools"]
