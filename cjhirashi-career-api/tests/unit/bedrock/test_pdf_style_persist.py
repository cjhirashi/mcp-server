"""pdf_style update must persist top-level style_guide; chat text is not a write."""
from services.bedrock.agent_loop import persist_nudge_text, should_nudge_pdf_persist, should_nudge_persist
from services.bedrock.agent_profiles import (
    AGENT_METHODOLOGIES,
    AGENT_ORCHESTRATOR,
    AGENT_PDF_DESIGN,
    AGENT_PROFESSIONAL_IDENTITY,
    get_profile,
)
from services.bedrock.prompt import _L2_DOMAIN_RULE
from services.bedrock.tools import _PDF_STYLE_UPDATE_FIELDS, converse_tool_specs, merge_writable_fields


def test_merge_accepts_top_level_style_guide():
    fields = merge_writable_fields(
        {"action": "update", "style_id": "pds-1", "style_guide": "# Guía\n- `.card`"},
        _PDF_STYLE_UPDATE_FIELDS,
    )
    assert fields == {"style_guide": "# Guía\n- `.card`"}


def test_merge_accepts_nested_fields():
    fields = merge_writable_fields(
        {"action": "update", "style_id": "pds-1", "fields": {"style_guide": "nested", "title": "T"}},
        _PDF_STYLE_UPDATE_FIELDS,
    )
    assert fields["style_guide"] == "nested"
    assert fields["title"] == "T"


def test_merge_top_level_overrides_nested():
    fields = merge_writable_fields(
        {
            "fields": {"style_guide": "old"},
            "style_guide": "new",
        },
        _PDF_STYLE_UPDATE_FIELDS,
    )
    assert fields == {"style_guide": "new"}


def test_merge_ignores_unknown_and_action_keys():
    fields = merge_writable_fields(
        {"action": "update", "style_id": "pds-1", "bogus": "x"},
        _PDF_STYLE_UPDATE_FIELDS,
    )
    assert fields == {}


def test_pdf_style_schema_keeps_required_inside_schema():
    specs = converse_tool_specs({"pdf_style"})
    schema = specs[0]["toolSpec"]["inputSchema"]["json"]
    assert schema["required"] == ["action"]
    assert "style_guide" in schema["properties"]


def test_pdf_design_suffix_requires_tool_update():
    suffix = get_profile(AGENT_PDF_DESIGN).system_prompt_suffix
    assert "pdf_style" in suffix
    assert "action=update" in suffix
    assert "NO guarda" in suffix
    assert "Tools reales:" in suffix


def test_nudge_when_pdf_design_has_write_intent_and_no_write():
    assert should_nudge_pdf_persist(
        AGENT_PDF_DESIGN,
        "Estamos trabajando con pds-1, genera la guía de clases",
        [],
        False,
    )


def test_no_nudge_after_successful_write_or_other_profile():
    assert not should_nudge_pdf_persist(
        AGENT_PDF_DESIGN,
        "genera la guía",
        ["pdf-template-styles"],
        False,
    )
    # L1 (orquestador) no tiene CRUD propio: nunca es elegible para el nudge.
    assert not should_nudge_pdf_persist(AGENT_ORCHESTRATOR, "genera la guía", [], False)
    assert not should_nudge_pdf_persist(AGENT_PDF_DESIGN, "genera la guía", [], True)
    assert not should_nudge_pdf_persist(AGENT_PDF_DESIGN, "¿qué clases tiene pds-1?", [], False)


def test_methodologies_suffix_requires_tool_update():
    suffix = get_profile(AGENT_METHODOLOGIES).system_prompt_suffix
    assert "update_career_record" in suffix
    assert "operational-methodologies" in suffix
    assert "NO guarda" in suffix
    assert "fields.content" in suffix


def test_l2_domain_rule_forbids_chat_as_write():
    assert "no persiste" in _L2_DOMAIN_RULE
    assert "update_career_record" in _L2_DOMAIN_RULE


def test_nudge_when_assistant_claims_write_without_tool():
    claim = "Perfecto. Ahora actualizo **opm-57** con un enfoque puro en Diseño de Plantillas PDF:"
    assert should_nudge_persist(AGENT_METHODOLOGIES, "ok", [], False, claim)
    assert should_nudge_persist(AGENT_METHODOLOGIES, "procede", [], False, claim)
    assert persist_nudge_text(AGENT_METHODOLOGIES).startswith("Eso quedó solo en el chat")
    assert "update_career_record" in persist_nudge_text(AGENT_METHODOLOGIES)


def test_nudge_methodologies_on_procede_even_without_claim():
    assert should_nudge_persist(AGENT_METHODOLOGIES, "procede", [], False, "")
    assert not should_nudge_persist(AGENT_METHODOLOGIES, "ok", [], False, "")
    assert not should_nudge_persist(AGENT_METHODOLOGIES, "ok", [], False, "¿en qué te ayudo?")


def test_nudge_identity_on_assistant_claim():
    claim = "Ahora actualizo ach-17 con la bio nueva."
    assert should_nudge_persist(AGENT_PROFESSIONAL_IDENTITY, "ok", [], False, claim)


def test_nudge_identity_on_user_proceed_without_claim():
    # Cualquier L2 write-enabled se beneficia del nudge por intención del
    # usuario, no solo pdf_design/methodologies (antes quedaba fuera y el
    # agente podía anunciar un write y no ejecutarlo nunca).
    assert should_nudge_persist(AGENT_PROFESSIONAL_IDENTITY, "procede", [], False, "")


def test_nudge_identity_on_bulk_reclassification_claim():
    # Regresión: "voy a reclasificar" / "actualizando cada una" no hacían
    # match con el regex original (solo cubría actualizar/guardar/escribir/
    # crear/documentar), así que un plan de escritura en lote nunca disparaba
    # el nudge y el agente se quedaba solo anunciando el trabajo.
    claim = (
        "Perfecto. Voy a reclasificar todas las 72 competencias en las 4 categorías "
        "solicitadas: Técnicas, Blandas, Dominio y Herramientas."
    )
    assert should_nudge_persist(AGENT_PROFESSIONAL_IDENTITY, "hazlo ya", [], False, claim)
    claim2 = "Ahora voy a reclasificar todas las competencias. Actualizando cada una con su categoría:"
    assert should_nudge_persist(AGENT_PROFESSIONAL_IDENTITY, "hazlo ya", [], False, claim2)
    assert "bulk_update_career_record" in persist_nudge_text(AGENT_PROFESSIONAL_IDENTITY)
