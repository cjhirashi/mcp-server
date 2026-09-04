"""Regresión real: un tool_use grande (bulk_update_career_record con ~69
items) se cortó por el límite de maxTokens (4096) a mitad de generación.
Bedrock descarta el bloque de contenido incompleto entero — el turno vuelve
sin texto NI tool_use (stop_reason="max_tokens"), indistinguible en el chat
de "el agente no hizo nada". should_nudge_persist/should_nudge_progress no
disparan porque ambos requieren texto no vacío; hacía falta un chequeo
propio para este caso."""
from services.bedrock.agent_loop import (
    _MAX_TOKENS_RETRY_BUDGET,
    _MAX_TOKENS_TRUNCATION_NUDGE,
    should_retry_max_tokens,
)
from services.bedrock.converse_client import _build_converse_kwargs
from config import settings


def test_retries_on_max_tokens_with_budget_left():
    assert should_retry_max_tokens("max_tokens", 0)
    assert should_retry_max_tokens("max_tokens", _MAX_TOKENS_RETRY_BUDGET - 1)


def test_stops_retrying_once_budget_exhausted():
    assert not should_retry_max_tokens("max_tokens", _MAX_TOKENS_RETRY_BUDGET)


def test_no_retry_for_ordinary_end_turn():
    # end_turn con tool_uses vacío y texto vacío es un caso distinto (lo
    # cubren should_nudge_persist/should_nudge_progress, o simplemente no hay
    # nada que decir) — este chequeo es específico de max_tokens.
    assert not should_retry_max_tokens("end_turn", 0)


def test_truncation_nudge_asks_for_smaller_batches():
    assert "bulk_update_career_record" in _MAX_TOKENS_TRUNCATION_NUDGE
    assert "tandas" in _MAX_TOKENS_TRUNCATION_NUDGE


def test_default_output_budget_is_well_above_bedrock_default():
    # 4096 (default histórico de converse_client.converse) es insuficiente
    # para un tool_use de ~69 items; el default de settings debe ser mayor.
    assert settings.BEDROCK_MAX_OUTPUT_TOKENS > 4096


def test_converse_kwargs_carry_the_configured_max_tokens():
    kwargs = _build_converse_kwargs(
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        messages=[{"role": "user", "content": [{"text": "hola"}]}],
        system_prompt="system",
        tools=[],
        max_tokens=8192,
        force_tool_use=False,
    )
    assert kwargs["inferenceConfig"]["maxTokens"] == 8192
