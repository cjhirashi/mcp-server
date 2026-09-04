"""feature 002 · RF-011/RF-012/D-8 — contrato de delegación de `purpose` hacia
`agent_visual_design`. `delegate_to_specialist` es de un solo golpe (sin ida y
vuelta L2<->L3 dentro del turno): el delegante debe declarar el `purpose` de su
dominio explícitamente, y el agente Visual no debe adivinarlo si no viene claro."""
import pytest

from services.bedrock.agent_profiles import (
    AGENT_CONFIGURATION,
    AGENT_DIGITAL_PRESENCE,
    AGENT_PROFESSIONAL_IDENTITY,
    AGENT_SEARCH_OPERATIONS,
    AGENT_VISUAL_DESIGN,
    get_profile,
)


@pytest.mark.requisito("RF-011")
def test_delegating_profiles_state_purpose():
    assert "purpose=proyectos" in get_profile(AGENT_PROFESSIONAL_IDENTITY).system_prompt_suffix
    assert "purpose=publicaciones" in get_profile(AGENT_DIGITAL_PRESENCE).system_prompt_suffix
    assert "purpose=agentes" in get_profile(AGENT_CONFIGURATION).system_prompt_suffix


@pytest.mark.requisito("RF-012")
def test_visual_asks_when_purpose_ambiguous():
    suffix = get_profile(AGENT_VISUAL_DESIGN).system_prompt_suffix.lower()
    assert "purpose" in suffix
    assert "pregunta" in suffix or "aclaraci" in suffix


@pytest.mark.requisito("D-8")
def test_search_operations_no_longer_mentions_images():
    suffix = get_profile(AGENT_SEARCH_OPERATIONS).system_prompt_suffix
    assert "agent_visual_design" not in suffix
