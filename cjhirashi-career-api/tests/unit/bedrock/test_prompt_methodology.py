"""Metodologías asignadas al agente se inyectan en el system prompt (no hardcoded)."""
from unittest.mock import MagicMock

import pytest

from services.bedrock.agent_profiles import (
    AGENT_CV_WRITING,
    AGENT_METHODOLOGIES,
    AGENT_ORCHESTRATOR,
    AGENT_PDF_DESIGN,
    AGENT_PDF_RENDER,
    AGENT_PROFESSIONAL_IDENTITY,
    get_profile,
    list_profiles,
    profile_can_search_knowledge,
)
from services.bedrock.prompt import methodology_assignment_block
from services.bedrock.tools import converse_tool_specs
from services.bedrock_service import default_system_prompt


def test_assignment_block_lists_assigned_titles_not_hardcoded_section():
    profile = get_profile(AGENT_PDF_DESIGN)
    block = methodology_assignment_block(
        profile,
        [
            {
                "id": "opm-99",
                "title": "Nueva convención de márgenes",
                "section": "Diseño PDF",
                "shared": False,
            },
            {
                "id": "opm-1",
                "title": "Protocolo compartido",
                "section": None,
                "shared": True,
            },
        ],
    )
    # La regla "solo las asignadas a ti" ahora vive en default_global_rules()
    # (ver test_global_rules.py), no en el bloque de catálogo en sí.
    assert "`agent_pdf_design`" in block
    assert "opm-99: Nueva convención de márgenes" in block
    assert "opm-1: Protocolo compartido" in block
    assert "(compartida)" in block
    assert "search_knowledge_base" in block


def test_assignment_block_empty_catalog_still_instructs_to_consult_future_ones():
    block = methodology_assignment_block(get_profile(AGENT_PROFESSIONAL_IDENTITY), [])
    assert "`agent_professional_identity`" in block
    assert "Cuando Carlos te asigne una desde el Admin" in block


def test_guardian_sees_all_and_assigns():
    block = methodology_assignment_block(get_profile(AGENT_METHODOLOGIES), [])
    assert "guardián" in block
    assert "agent_profile_ids" in block


def test_orchestrator_does_not_claim_search_tool():
    block = methodology_assignment_block(get_profile(AGENT_ORCHESTRATOR), [])
    assert "No tienes search_knowledge_base" in block
    assert "asignadas a su propio perfil" in block


def test_every_profile_gets_assignment_block_starting_with_its_id():
    """The global "solo las asignadas a ti" rule itself is now shared across
    all profiles via default_global_rules() (see test_global_rules.py); this
    block only carries the per-profile catalog framing."""
    for profile in list_profiles():
        block = methodology_assignment_block(profile, None)
        assert block.startswith(f"Tu perfil es `{profile.id}`.")


def test_profile_can_search_knowledge_matches_tools():
    assert profile_can_search_knowledge(get_profile(AGENT_PROFESSIONAL_IDENTITY))
    assert profile_can_search_knowledge(get_profile(AGENT_PDF_DESIGN))
    assert profile_can_search_knowledge(get_profile(AGENT_CV_WRITING))
    assert not profile_can_search_knowledge(get_profile(AGENT_ORCHESTRATOR))
    assert not profile_can_search_knowledge(get_profile(AGENT_PDF_RENDER))


def test_pdf_suffix_does_not_hardcode_section_as_search_target():
    suffix = get_profile(AGENT_PDF_DESIGN).system_prompt_suffix
    assert "en «Diseño PDF»" not in suffix
    assert "asignadas a este perfil" in suffix


def test_default_prompt_consults_only_assigned_methodologies():
    text = default_system_prompt()
    assert "SOLO las metodologías operativas asignadas a tu perfil" in text
    assert "agent_profile_ids" in text
    assert "también son tuyas para mantener" not in text


def test_search_tool_description_scopes_to_caller():
    specs = converse_tool_specs(
        {"search_knowledge_base"},
        caller_profile=get_profile(AGENT_PDF_DESIGN),
    )
    description = specs[0]["toolSpec"]["description"]
    assert "agent_pdf_design" in description
    assert "agent_profile_ids" in description

    guardian = converse_tool_specs(
        {"search_knowledge_base"},
        caller_profile=get_profile(AGENT_METHODOLOGIES),
    )
    assert "TODAS las metodologías" in guardian[0]["toolSpec"]["description"]


@pytest.mark.asyncio
async def test_compose_injects_assigned_catalog(monkeypatch):
    from services.bedrock import prompt

    async def fake_override(_db):
        return None

    async def fake_global_rules_override(_db):
        return None

    async def fake_suffix(_db, profile):
        return profile.system_prompt_suffix

    async def fake_list(_db, _user_id, caller_id):
        assert caller_id == AGENT_PDF_DESIGN
        return [
            {
                "id": "opm-88",
                "title": "Metodología recién asignada",
                "section": "Calidad",
                "shared": False,
            }
        ]

    async def fake_notes(_user_id, _profile_id, limit=40):
        return [{"id": "1", "text": "Prefiere tono directo"}]

    monkeypatch.setattr(prompt, "get_system_prompt_override", fake_override)
    monkeypatch.setattr(prompt, "get_global_rules_override", fake_global_rules_override)
    monkeypatch.setattr(prompt.profile_prompts, "get_effective_suffix", fake_suffix)
    monkeypatch.setattr(
        "services.methodology_scope.list_assigned_methodologies",
        fake_list,
    )
    monkeypatch.setattr(
        "services.bedrock.local_memory.list_agent_notes",
        fake_notes,
    )

    composed = await prompt.compose_system_prompt(
        MagicMock(),
        get_profile(AGENT_PDF_DESIGN),
        None,
        user_id="usr-1",
    )
    assert "opm-88: Metodología recién asignada [Calidad]" in composed
    assert "solo las asignadas a ti" in composed
    assert "SOLO las metodologías operativas asignadas a tu perfil" in composed
    assert "Prefiere tono directo" in composed
    assert "MEMORIA PROPIA" in composed


@pytest.mark.requisito("RF-018")
def test_block_guides_search_then_read_one_methodology():
    """El bloque instruye buscar→leer: extractos con search, la metodología
    que aplica se lee entera con get_career_record, una por trabajo."""
    profile = get_profile(AGENT_PROFESSIONAL_IDENTITY)
    assert profile_can_search_knowledge(profile)
    block = methodology_assignment_block(
        profile, [{"id": "opm-1", "title": "Proceso 1", "section": "Identidad"}]
    )
    low = block.lower()
    assert "search_knowledge_base" in block
    assert "get_career_record" in block
    assert "extracto" in low  # devuelve extractos, no el contenido completo
    # "una por trabajo, no todas"
    assert "no todas" in low or "una por trabajo" in low


@pytest.mark.requisito("RF-018")
def test_block_without_search_tool_unchanged_guidance():
    profile = get_profile(AGENT_PDF_RENDER)  # L3 sin search_knowledge_base
    assert not profile_can_search_knowledge(profile)
    block = methodology_assignment_block(profile, [])
    assert "No tienes search_knowledge_base" in block
