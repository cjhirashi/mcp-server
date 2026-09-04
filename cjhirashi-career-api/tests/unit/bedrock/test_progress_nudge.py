"""El agente se quedaba anunciando el próximo paso ("ahora voy a obtener el
campo nivel de cada una...") turno tras turno sin ejecutarlo nunca, incluso
en tareas de solo lectura donde should_nudge_persist no aplica (no hay write
reivindicado). should_nudge_progress cubre ese estancamiento genérico."""
from services.bedrock.agent_loop import _PROGRESS_STALL_NUDGE, should_nudge_progress

L2 = 2
L1 = 1


def test_nudges_on_announced_next_step_without_action():
    # Caso real reportado: perfil L2, sin intención de detenerse del usuario.
    text = (
        "Excelente, tengo todas las 69 competencias. Ahora voy a obtener el campo "
        "nivel de cada una para ver qué valores están usando actualmente:"
    )
    assert should_nudge_progress(L2, "Intenta de nuevo", text, 0)


def test_nudges_on_trailing_colon_even_without_verb_match():
    text = "Voy a revisar cada competencia y su nivel actual:"
    assert should_nudge_progress(L2, "continúa", text, 0)


def test_no_nudge_when_user_asks_to_stop():
    text = "Ahora voy a obtener el campo nivel de cada una:"
    assert not should_nudge_progress(L2, "detente, ya no sigas con esto", text, 0)


def test_no_nudge_when_negated():
    # "no voy a continuar" no es un anuncio pendiente de ejecutar.
    text = "Entendido, no voy a continuar con la reclasificación."
    assert not should_nudge_progress(L2, "ok", text, 0)


def test_no_nudge_past_budget():
    text = "Ahora voy a revisar cada una:"
    assert not should_nudge_progress(L2, "sigue", text, 2)  # ya se usaron los 2 empujones


def test_no_nudge_for_level_1():
    # L1 (orquestador) no ejecuta tools directamente sobre career records.
    text = "Ahora voy a obtener el campo nivel de cada una:"
    assert not should_nudge_progress(L1, "sigue", text, 0)


def test_no_nudge_on_finished_summary():
    text = "Listo: actualicé el nivel de las 69 competencias según lo acordado."
    assert not should_nudge_progress(L2, "gracias", text, 0)


def test_nudge_text_mentions_pagination_and_bulk_tool():
    assert "list_career_record" in _PROGRESS_STALL_NUDGE
    assert "bulk_update_career_record" in _PROGRESS_STALL_NUDGE
