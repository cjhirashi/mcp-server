"""
System prompt — default, override PG, suffix por perfil y sección.
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bedrock_settings import BedrockSettings
from services.bedrock.agent_profiles import (
    AgentProfile,
    AGENT_METHODOLOGIES,
    AGENT_SEARCH_OPERATIONS,
    AGENT_VACANCY_SEARCH,
    delegation_targets,
    get_profile,
    profile_can_search_knowledge,
)
from services.bedrock import profile_prompts

logger = logging.getLogger(__name__)

# ============================================================================
# Reglas de prompt del sistema
# ============================================================================

JOB_DISCOVERY_AUTH_RULE = (
    "Vacantes descubiertas: run_job_discovery solo hace preview (refs L1, L2…). "
    "Presenta empresa, rol, fuente y URL. No llames save_job_listings hasta que Carlos "
    "autorice refs concretas. save_job_listings(refs=...) crea vacancies pending_review "
    "para seguimiento en Vacantes. Nunca inventes vacantes ni uses create_career_record "
    "para ofertas de un discovery. Si Carlos pega una URL de vacante, importar y guardar "
    "esa ref sí está autorizado."
)

GROUNDING_RULE = (
    "REGLA CRÍTICA — NO ALUCINAR: Los datos de carrera viven en PostgreSQL, no en tu "
    "entrenamiento. Nunca inventes registros, IDs, títulos, fechas ni contenido. "
    "Antes de afirmar algo sobre un registro concreto (ej. ach-17, vac-5), consulta "
    "herramientas o el especialista dueño del dominio. Si la herramienta o el sub-turno "
    "devuelve not_found o vacío, dilo — no rellenes con suposiciones. Los IDs son "
    "prefijados (ach-17, cmp-42, trl-3)."
)

_L1_ORCHESTRATION_RULE = (
    "Nivel 1: no tienes CRUD ni tools de tarea. Cada pedido de datos o escritura "
    "se resuelve con delegate_to_specialist al L2 de esa área o al L3 de esa tarea. "
    "No respondas listados ni cifras de carrera sin haber delegado en este turno."
)

_L2_DOMAIN_RULE = (
    "Nivel 2: opera solo tu dominio. No llames a otro L2 ni al orquestador. "
    "Tareas transversales (bitácora, PDF de un registro, imágenes, plan de tareas, "
    "publicación LinkedIn, discovery de vacantes, redacción de CV o cover letter, "
    "consulta web, repos GitHub) se delegan a L3. "
    "Si piden listar TODO un recurso de tu dominio, usa list_career_record con limit=100 y pagina mientras "
    "has_more sea true. "
    "Si preguntan CUÁNTOS hay, llama count_career_records. "
    "Si necesitas revisar una o dos columnas puntuales (ej. nivel, category) en TODOS los "
    "registros de un resource_key, usa list_career_record con fields=['esa_columna'] — UNA "
    "llamada trae esa columna en cada item. Nunca hagas un get_career_record por cada registro "
    "para leer el mismo campo en todos: con 60-70 registros eso agota las rondas del turno antes "
    "de llegar a escribir nada."
    "Redactar en el chat no persiste: usa create_career_record o update_career_record "
    "(en diseño PDF: pdf_style / pdf_template). No afirmes que guardaste hasta que la tool "
    "devuelva el id. Si el usuario confirma (procede, adelante, hazlo), llama la tool en este turno. "
    "Si el cambio toca varios registros del mismo resource_key (ej. reclasificar todas las "
    "competencias en categorías nuevas), NO los anuncies uno por uno en texto: llama "
    "bulk_update_career_record con resource_key y updates=[{record_id, fields}, ...] en el mismo "
    "turno en que lo confirmas. 'Voy a actualizar cada uno' sin llamar la tool no cuenta como hecho. "
    "Esto también aplica a tareas de solo lectura o análisis sobre muchos registros: no termines "
    "el turno diciendo 'ahora voy a revisar/obtener X de cada uno' y te detengas ahí — ejecútalo "
    "en el mismo turno, ronda tras ronda, hasta terminar el lote completo o hasta que de verdad "
    "necesites que Carlos decida algo. Anunciar el próximo paso sin darlo no es progreso."
)

_L3_TASK_RULE = (
    "Nivel 3: no hablas con el usuario. Ejecuta la tarea con tus tools y devuelve "
    "un resumen factual (ids, URLs, errores). No delegues."
)

_METHODOLOGY_ASSIGNMENT_RULE = (
    "METODOLOGÍAS OPERATIVAS — solo las asignadas a ti. "
    "Cada metodología tiene `agent_profile_ids` (Admin Panel → Metodologías Operativas → Agentes). "
    "Las tuyas son las que incluyen tu perfil, más las compartidas (lista vacía = todos los agentes). "
    "No consultes ni apliques metodologías asignadas solo a otros agentes. "
    "Si Carlos crea una metodología nueva y te la asigna, es tuya de inmediato: consúltala y síguela. "
    "La asignación vive en el Admin, no en el código; no esperes que este prompt nombre cada metodología. "
    "Esta regla tiene prioridad sobre cualquier mención a una sección de metodología en el resto del prompt."
)


def methodology_assignment_block(
    profile: AgentProfile,
    assigned: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Regla + catálogo vigente. El catálogo se recarga cada turno desde PG."""
    lines = [f"Tu perfil es `{profile.id}`."]
    if profile.id == AGENT_METHODOLOGIES:
        lines.append(
            "Eres el guardián: ves y mantienes TODAS las metodologías. "
            "Al crear o editar, llena agent_profile_ids con el agente dueño; "
            "vacío = compartida."
        )
    if assigned:
        lines.append("Metodologías vigentes que te corresponden (catálogo actualizado cada turno):")
        for row in assigned:
            section = f" [{row['section']}]" if row.get("section") else ""
            shared = " (compartida)" if row.get("shared") else ""
            lines.append(f"- {row['id']}: {row['title']}{section}{shared}")
    else:
        lines.append(
            "En este momento no hay metodologías listadas para ti. "
            "Cuando Carlos te asigne una desde el Admin, aparecerá aquí y deberás consultarla."
        )
    if profile_can_search_knowledge(profile):
        lines.append(
            "Antes de operar una tabla o protocolo, llama search_knowledge_base "
            "con type=methodology. La tool ya filtra a las asignadas a tu perfil "
            "(el guardián ve todas). Si el catálogo trae una metodología nueva, consúltala: es tuya."
        )
    else:
        lines.append(
            "No tienes search_knowledge_base. Los especialistas que sí la tienen "
            "consultan solo las metodologías asignadas a su propio perfil."
        )
    return "\n".join(lines)


def _agent_memory_block(notes: List[Dict[str, Any]]) -> str:
    if not notes:
        return (
            "MEMORIA PROPIA: Carlos puede dejar notas para este perfil en el "
            "catálogo de agentes. Ahora mismo no hay ninguna."
        )
    lines = ["MEMORIA PROPIA (notas de Carlos para este perfil; consúltalas siempre):"]
    for note in notes:
        text = (note.get("text") or "").strip()
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines)


def _delegation_catalog_block(
    profile: AgentProfile,
    target_ids: Optional[List[str]] = None,
) -> str:
    if target_ids is None:
        targets = delegation_targets(profile)
    else:
        targets = []
        for tid in target_ids:
            try:
                targets.append(get_profile(tid))
            except KeyError:
                continue
    if not targets:
        return "Este perfil no tiene especialistas configurados para delegar."
    lines = [f"- {p.id} (L{p.level}) — {p.label}" for p in targets]
    return "Especialistas a los que puedes delegar:\n" + "\n".join(lines)


# ============================================================================
# Prompt base y override desde PG
# ============================================================================

def default_system_prompt() -> str:
    """Prompt base completo — misma fuente que /bedrock/instructions."""
    from services import bedrock_service

    return bedrock_service.default_system_prompt()


async def get_system_prompt_override(db: AsyncSession) -> Optional[str]:
    result = await db.execute(select(BedrockSettings).limit(1))
    row = result.scalar_one_or_none()
    return row.system_prompt if row and row.system_prompt else None


def default_global_rules() -> str:
    """Reglas globales (todo agente, cualquier nivel/perfil) — GET/PUT
    /bedrock/global-rules. Reemplazo total, no aditivo, igual que el prompt base."""
    return "\n\n".join([GROUNDING_RULE, _METHODOLOGY_ASSIGNMENT_RULE])


async def get_global_rules_override(db: AsyncSession) -> Optional[str]:
    result = await db.execute(select(BedrockSettings).limit(1))
    row = result.scalar_one_or_none()
    return row.global_rules if row and row.global_rules else None


# ============================================================================
# Composición del system prompt
# ============================================================================

async def compose_system_prompt(
    db: AsyncSession,
    profile: AgentProfile,
    page_context: Optional[dict],
    user_id: Optional[str] = None,
    delegate_ids: Optional[List[str]] = None,
) -> str:
    base = await get_system_prompt_override(db) or default_system_prompt()
    global_rules = await get_global_rules_override(db) or default_global_rules()
    suffix = await profile_prompts.get_effective_suffix(db, profile)
    assigned: List[Dict[str, Any]] = []
    if user_id:
        try:
            from services.methodology_scope import list_assigned_methodologies

            assigned = await list_assigned_methodologies(db, user_id, profile.id)
        except Exception:
            logger.warning(
                "No se pudo cargar el catálogo de metodologías para %s",
                profile.id,
                exc_info=True,
            )
    parts = [
        base,
        "Las reglas de nivel de este perfil tienen prioridad sobre el prompt global si hay conflicto.",
        global_rules,
        methodology_assignment_block(profile, assigned),
        suffix,
    ]
    if user_id and profile.user_facing:
        try:
            from services.bedrock.local_memory import list_agent_notes

            notes = await list_agent_notes(user_id, profile.id)
            parts.append(_agent_memory_block(notes))
        except Exception:
            logger.warning(
                "No se pudo cargar la memoria propia de %s",
                profile.id,
                exc_info=True,
            )
    if page_context and page_context.get("resource_key"):
        title = page_context.get("page_title") or page_context["resource_key"]
        parts.append(
            f"El usuario está en {title} (resource_key={page_context['resource_key']}). "
            "Prioriza operaciones sobre ese recurso salvo que pida otra cosa."
        )
    route = (page_context or {}).get("route") or ""
    if profile.level == 1:
        parts.append(_L1_ORCHESTRATION_RULE)
        parts.append(_delegation_catalog_block(profile, delegate_ids))
    elif profile.level == 2:
        parts.append(_L2_DOMAIN_RULE)
        parts.append(_delegation_catalog_block(profile, delegate_ids))
    else:
        parts.append(_L3_TASK_RULE)
    if profile.id in (AGENT_SEARCH_OPERATIONS, AGENT_VACANCY_SEARCH) or route == "/job-discovery":
        parts.append(JOB_DISCOVERY_AUTH_RULE)
    return "\n\n".join(p for p in parts if p)
