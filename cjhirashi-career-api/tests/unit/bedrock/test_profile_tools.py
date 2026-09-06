"""Override de herramientas por perfil (profile_tools)."""
import pytest

from services.bedrock.agent_profiles import (
    AGENT_ORCHESTRATOR,
    AGENT_PROFESSIONAL_IDENTITY,
    AGENT_VISUAL_DESIGN,
    get_profile,
    tools_for_profile,
)
from services.bedrock import tools as bedrock_tools
from services.bedrock.profile_tools import (
    default_tool_names,
    effective_tool_names,
    list_builtin_tool_catalog,
    validate_tool_names,
)


def test_default_tool_names_match_code():
    profile = get_profile(AGENT_PROFESSIONAL_IDENTITY)
    assert default_tool_names(profile) == tools_for_profile(
        profile, bedrock_tools.all_tool_names()
    )


def test_effective_without_override_is_default():
    profile = get_profile(AGENT_PROFESSIONAL_IDENTITY)
    assert effective_tool_names(profile, None) == default_tool_names(profile)


def test_effective_override_replaces_default():
    profile = get_profile(AGENT_PROFESSIONAL_IDENTITY)
    # L2 delega → delegate_to_specialist se añade al override
    assert effective_tool_names(profile, ["list_career_record"]) == {
        "list_career_record",
        "delegate_to_specialist",
    }
    # un tool que el default tenía (search_knowledge_base) ya no está
    assert "search_knowledge_base" not in effective_tool_names(
        profile, ["list_career_record"]
    )


def test_delegate_rule_by_level_after_override():
    l3 = get_profile(AGENT_VISUAL_DESIGN)
    assert l3.level == 3
    # L3 no delega → delegate_to_specialist se descarta aunque esté en el override
    assert "delegate_to_specialist" not in effective_tool_names(
        l3, ["generate_image", "delegate_to_specialist"]
    )
    assert effective_tool_names(l3, ["generate_image"]) == {"generate_image"}


def test_override_ignores_unknown_tool_names():
    profile = get_profile(AGENT_PROFESSIONAL_IDENTITY)
    result = effective_tool_names(profile, ["list_career_record", "not_a_tool"])
    assert "not_a_tool" not in result
    assert "list_career_record" in result


def test_validate_tool_names_normalizes_and_dedupes():
    assert validate_tool_names(
        ["list_career_record", "get_career_record", "list_career_record"]
    ) == ["get_career_record", "list_career_record"]


def test_validate_tool_names_rejects_unknown():
    with pytest.raises(ValueError):
        validate_tool_names(["list_career_record", "not_a_tool"])


def test_orchestrator_default_is_delegate_only():
    profile = get_profile(AGENT_ORCHESTRATOR)
    assert default_tool_names(profile) == {"delegate_to_specialist"}
    # D-4: el operador puede añadir tools al L1 desde el override
    assert effective_tool_names(profile, ["list_career_record"]) == {
        "list_career_record",
        "delegate_to_specialist",
    }


def test_list_builtin_tool_catalog_has_name_and_description():
    catalog = list_builtin_tool_catalog()
    assert len(catalog) == len(bedrock_tools.all_tool_names())
    assert all("name" in t and "description" in t for t in catalog)
    names = {t["name"] for t in catalog}
    assert "list_career_record" in names
    assert "search_knowledge_base" in names
