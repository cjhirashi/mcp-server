"""
Loop agente local — Converse + tools + historial PG + delegación.

Punto de entrada del Harness local. Ver ADR-008.
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.bedrock import agent_profiles, budget, converse_client, history_manager, prompt, section_profiles
from services.bedrock import settings_loader, tools, usage_logger
from services.bedrock.agent_profiles import (
    list_profiles,
    AGENT_PDF_DESIGN,
    AGENT_METHODOLOGIES,
)
from services.bedrock.delegation import run_specialist_sub_turn
from services.bedrock.attachments import build_user_content_blocks
from services.bedrock.errors import BedrockBudgetExceeded, BedrockError

logger = logging.getLogger(__name__)

# ============================================================================
# Constantes de estado de tools
# ============================================================================

_TOOL_STATUS = {
    "describe_resource_schema": "Revisando la estructura de la tabla...",
    "search_knowledge_base": "Consultando la base de conocimiento...",
    "list_career_record": "Buscando registros...",
    "count_career_records": "Contando registros...",
    "get_career_record": "Consultando el registro...",
    "create_career_record": "Creando el registro...",
    "update_career_record": "Actualizando el registro...",
    "bulk_update_career_record": "Actualizando varios registros...",
    "delete_career_record": "Eliminando el registro...",
    "list_recent_changes": "Consultando la bitácora...",
    "restore_deleted_record": "Restaurando el registro...",
    "create_linkedin_post": "Publicando en LinkedIn...",
    "generate_image": "Generando imagen...",
    "delegate_to_specialist": "Consultando especialista...",
    "list_job_providers": "Revisando portales de vacantes...",
    "run_job_discovery": "Buscando vacantes...",
    "import_job_url": "Importando vacante por URL...",
    "save_job_listings": "Creando vacantes autorizadas...",
    "pdf_style": "Actualizando el estilo PDF...",
    "pdf_template": "Actualizando la plantilla PDF...",
    "generate_pdf": "Generando PDF...",
    "render_record_pdf": "Generando PDF del registro...",
    "list_pdf_capable_resources": "Revisando tablas con PDF...",
    "web_search": "Buscando en internet...",
    "web_fetch": "Leyendo la página...",
    "get_github_status": "Revisando la conexión GitHub...",
    "list_github_repos": "Listando repositorios GitHub...",
    "get_github_repo": "Consultando el repositorio...",
    "list_github_contents": "Listando archivos del repositorio...",
    "get_github_file": "Leyendo el archivo en GitHub...",
    "search_github_code": "Buscando código en GitHub...",
}

# Tools de solo lectura cuyo resultado no cambia dentro de un mismo turno: si el
# modelo repite la llamada idéntica, se le responde con una nota corta en vez de
# reejecutar y reincrustar el payload (control de tokens de entrada).
_DEDUP_READ_TOOLS = frozenset({
    "get_career_record",
    "list_career_record",
    "count_career_records",
    "describe_resource_schema",
    "search_knowledge_base",
})


# Si un L2 anuncia un write o el usuario pide guardar y el turno termina sin
# tool de escritura, un recordatorio (una vez) obliga a persistir.
# Ver should_nudge_persist. "ok" solo cuenta si el asistente reivindicó el write.
_USER_WRITE_INTENT = re.compile(
    r"(?i)\b(generar|generes|genera|guardar|guardes|guarda|actualizar|actualices|"
    r"actualiza|escribir|escribas|escribe|documentar|documenta|crear|crea|crees)\b"
)
_USER_PROCEED = re.compile(
    r"(?i)\b(procede|adelante|hazlo|apl[ií]calo|implementa(lo)?|contin[uú]a)\b"
)
_ASSISTANT_WRITE_CLAIM = re.compile(
    r"(?i)("
    r"ahora (actualizo|guardo|escribo|creo|reclasifico|clasifico|modifico|"
    r"cambio|reorganizo|muevo|asigno)|"
    r"voy a (actualizar|guardar|escribir|crear|documentar|reclasificar|clasificar|"
    r"modificar|cambiar|reorganizar|mover|asignar)|"
    r"procedo a (actualizar|guardar|escribir|reclasificar|clasificar|modificar)|"
    r"actualizo\s+(\*\*)?(opm|pds|pdt|cvv|clv)-|"
    r"(actualizando|reclasificando|clasificando|modificando|reorganizando|"
    r"asignando)\s+(el |la |los |las |cada |todas? )"
    r")"
)
# Se evalúa para cualquier L2 con write_enabled (no solo PDF/metodologías): un
# "hazlo"/"adelante" del usuario tras intención de escritura es la misma señal
# en cualquier dominio, y restringirlo a 2 perfiles dejaba sin nudge al resto
# (bug real: se reportó en agent_professional_identity).

_PDF_PERSIST_NUDGE = (
    "Eso quedó solo en el chat: PostgreSQL no se actualizó. "
    "Si el usuario pidió generar o guardar, llama ahora `pdf_style` o `pdf_template` "
    "con action=update (o create) y el contenido. "
    "Para la guía de clases usa action=update, style_id y style_guide con el Markdown. "
    "No afirmes que ya lo guardaste hasta que la tool devuelva el id."
)
_METHODOLOGIES_PERSIST_NUDGE = (
    "Eso quedó solo en el chat: PostgreSQL no se actualizó. "
    "Llama ahora update_career_record con resource_key='operational-methodologies', "
    "record_id (ej. opm-57) y fields.content con el Markdown completo. "
    "Si es uno nuevo, create_career_record con title, section y content. "
    "No afirmes que lo guardaste hasta que la tool devuelva el id."
)
_GENERIC_PERSIST_NUDGE = (
    "Eso quedó solo en el chat: PostgreSQL no se actualizó. "
    "Llama ahora create_career_record o update_career_record con resource_key, "
    "record_id si aplica, y fields. Si el cambio afecta varios registros del mismo "
    "resource_key (p.ej. reclasificar todas las X), usa bulk_update_career_record con "
    "resource_key y updates=[{record_id, fields}, ...] en vez de llamar update_career_record "
    "una por una — hazlo ahora, en este turno, no lo anuncies solamente. No afirmes que lo "
    "guardaste hasta que la tool devuelva el id o los ids."
)


def persist_nudge_text(profile_id: str) -> str:
    if profile_id == AGENT_PDF_DESIGN:
        return _PDF_PERSIST_NUDGE
    if profile_id == AGENT_METHODOLOGIES:
        return _METHODOLOGIES_PERSIST_NUDGE
    return _GENERIC_PERSIST_NUDGE


def _l2_write_profile_ids() -> set:
    return {p.id for p in list_profiles() if p.level == 2 and p.write_enabled}


def should_nudge_persist(
    profile_id: str,
    user_message: str,
    affected_resources: List[str],
    already_nudged: bool,
    assistant_text: str = "",
) -> bool:
    """True when an L2 writer ended a turn claiming/being asked to write, with no write."""
    if already_nudged or affected_resources:
        return False
    if profile_id not in _l2_write_profile_ids():
        return False
    head = (assistant_text or "")[:400]
    if _ASSISTANT_WRITE_CLAIM.search(head):
        return True
    text = user_message or ""
    return bool(_USER_WRITE_INTENT.search(text) or _USER_PROCEED.search(text))


def should_nudge_pdf_persist(
    profile_id: str,
    user_message: str,
    affected_resources: List[str],
    already_nudged: bool,
    assistant_text: str = "",
) -> bool:
    """Compat: mismo criterio que should_nudge_persist (histórico: solo PDF)."""
    return should_nudge_persist(
        profile_id, user_message, affected_resources, already_nudged, assistant_text
    )


# ============================================================================
# Dataclass que modela la solicitud de un turno de chat realizado por el usuario.
# Contiene el mensaje principal, contexto del chat, información de metadatos de página,
# perfil/agente relevante, modelo de IA preferido y anexos enviados junto al mensaje.
# Es usada como estructura base para manejar la información de cada petición de conversación.
# ============================================================================

@dataclass
class ChatTurnRequest:
    session_id: str                # ID único de la sesión de chat
    message: str                   # Mensaje enviado por el usuario (input principal)
    chat_surface: str = "contextual"         # Superficie/contexto del chat ("general", "contextual", etc.)
    page_context: Optional[Dict[str, Any]] = None  # Contexto adicional de la página/origen (metadatos relevantes)
    model_id: Optional[str] = None           # ID explícito del modelo solicitado (opcional, sugerido por cliente)
    agent_profile_id: Optional[str] = None   # Perfil/agente especializado solicitado (opcional)
    attachments: Optional[List[Dict[str, Any]]] = None  # Archivos adjuntos o bloques de contenido enviados junto al mensaje


# ============================================================================
# Resolución de modelo efectivo
# ============================================================================

def _effective_model(req: ChatTurnRequest, runtime, profile) -> str:
    """
    Determina el modelo de IA "efectivo" para una solicitud de turno de chat,
    teniendo en cuenta las preferencias del usuario, reglas de negocio y perfiles de agente.

    - Para chats "general", ignora modelos débiles sugeridos por el usuario y usa el default del perfil
      si existe y está permitido, o el modelo por defecto del runtime.
    - Para otras superficies/contextos:
      - Si el usuario sugirió un modelo permitido y no es "débil", se usa ese.
      - Si no, prefiere el modelo por defecto del perfil, si existe.
      - Si ningún criterio anterior aplica, recomienda modelo según el contexto de página.

    Args:
        req:   Instancia de ChatTurnRequest con la metadata del turno.
        runtime: Objeto con configuración actual de orquestador de modelos.
        profile: Perfil de agente asociado a la conversación.

    Returns:
        str: ID del modelo efectivo a utilizar.
    """
    # Modelos considerados demasiado "débiles" para chats generales.
    weak_models = {
        "amazon.nova-lite-v1:0",
    }

    # Si la superficie es "general", se prefiere explícitamente el modelo por defecto del perfil,
    # ignorando modelos débiles sugeridos por el cliente.
    if req.chat_surface == "general":
        # Usa el modelo por defecto del perfil si está definido y está permitido.
        if profile.default_model_id and profile.default_model_id in settings.BEDROCK_AVAILABLE_MODELS:
            return profile.default_model_id
        # Si no existe, cae al modelo por defecto definido a nivel de runtime.
        return runtime.orchestrator_model_id

    # En otros chats/contextos, si el usuario pide un modelo explícito permitido (y no débil), usarlo.
    if req.model_id and req.model_id in settings.BEDROCK_AVAILABLE_MODELS:
        if req.model_id not in weak_models:
            return req.model_id

    # Si el perfil tiene un modelo por defecto valido, usarlo.
    if profile.default_model_id and profile.default_model_id in settings.BEDROCK_AVAILABLE_MODELS:
        return profile.default_model_id

    # Como última opción, recomendar modelo basado en el contexto de página actual.
    return section_profiles.resolve_recommended_model(req.page_context)


# ============================================================================
# Turno síncrono
# ============================================================================

async def run_single_turn_sync(
    db: AsyncSession,
    *,
    user_id: str,
    session_id: str,
    message: str,
    chat_surface: str = "contextual",
    agent_profile_id: Optional[str] = None,
    page_context: Optional[dict] = None,
    model_id: Optional[str] = None,
    max_round_trips: Optional[int] = None,
    record_history: bool = True,
    load_session_history: Optional[bool] = None,
    delegation_depth: int = 0,
) -> Dict[str, Any]:
    """
    Ejecuta un único turno de conversación de manera síncrona (sin streaming SSE) utilizando el loop principal del agente Bedrock.

    Este método es utilizado típicamente para delegación interna o desde componentes que requieren la respuesta
    completa del agente en una sola llamada, sin la comunicación parcial por eventos SSE.

    Flujo interno:
        - Invoca el generador `chat_stream`, iterando sobre los eventos generados por el agente.
        - Si se recibe un evento de tipo "done", lo almacena como resultado final.
        - Si se recibe un evento de tipo "error", se lanza la excepción correspondiente.
        - Al finalizar, devuelve el resultado completo de la respuesta (evento "done").

    Args:
        db (AsyncSession): Sesión async de base de datos.
        user_id (str): ID del usuario que realiza la solicitud.
        session_id (str): ID de la conversación/sesión.
        message (str): Mensaje o input del usuario.
        chat_surface (str, opcional): Superficie del chat ("general", "contextual", etc.).
        agent_profile_id (str, opcional): ID del perfil de agente.
        page_context (dict, opcional): Contexto de página o metadata adicional.
        model_id (str, opcional): Modelo explícito a usar en la respuesta.
        max_round_trips (int, opcional): Rondas máximas permitidas para el ciclo de herramientas.
        record_history (bool, opcional): Si True, registra el turno en el historial.
        load_session_history (bool, opcional): Si None, sigue a record_history. False en sub-turnos.
        delegation_depth (int, opcional): Profundidad actual (0 user-facing, 1 primer hop, 2 L2→L3).

    Returns:
        Dict[str, Any]: Diccionario con la respuesta final generada (evento "done").
    
    Raises:
        BedrockError: Si se produce un error durante la generación del turno.
    """
    last: Dict[str, Any] = {}
    async for event in chat_stream(
        db,
        user_id,
        ChatTurnRequest(
            session_id=session_id,
            message=message,
            chat_surface=chat_surface,
            page_context=page_context,
            model_id=model_id,
            agent_profile_id=agent_profile_id,
        ),
        max_round_trips_override=max_round_trips,
        record_history=record_history,
        load_session_history=load_session_history,
        delegation_depth=delegation_depth,
    ):
        if event["type"] == "done":
            last = event
        elif event["type"] == "error":
            raise BedrockError(event["message"])
    return last


# ============================================================================
# Turno con streaming SSE
# ============================================================================

async def chat_stream(
    db: AsyncSession,
    user_id: str,
    req: ChatTurnRequest,
    *,
    max_round_trips_override: Optional[int] = None,
    record_history: bool = True,
    load_session_history: Optional[bool] = None,
    delegation_depth: int = 0,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Generador asincrónico de eventos para manejar el ciclo de conversación del agente con soporte para SSE (Server-Sent Events).
    
    Esta función permite procesar turnos de conversación entre un usuario y un agente, soportando múltiples rondas, 
    llamadas a herramientas y delegaciones a especialistas, todo en modalidad de streaming asíncrono. Produce distintos 
    eventos a lo largo del proceso, notificando sobre el estado, delegaciones, errores y la respuesta final.

    Flujo principal:
        1. Prepara el contexto de ejecución: recupera historial, perfil de agente, herramientas permitidas y mensaje actual.
        2. (Opcional) Registra o recupera la conversación en la BD, si record_history=True.
        3. Itera hasta un máximo de rondas (max_rounds): 
            - Llama al modelo conversacional para obtener la siguiente acción (respuesta o uso de herramienta).
            - Si hay error con Bedrock, emite un evento de error y termina.
            - Si el agente responde directamente (stop_reason != tool_use):
                - Registra uso y mensajes en historial, si corresponde.
                - Emite evento "done" con la respuesta final y termina.
            - Si requiere herramientas:
                - Para cada uso de herramienta:
                    - Si es delegación a especialista, ejecuta sub-turno y emite eventos de inicio/fin.
                    - Si es herramienta normal, la ejecuta y agrega resultados.
                    - Acumula recursos afectados e invalidaciones.
                - Agrega los resultados de herramientas al nuevo contexto para la siguiente ronda.
        4. Si se agotan las vueltas sin respuesta final, emite un evento de error.

    Args:
        db (AsyncSession): Sesión asíncrona de base de datos.
        user_id (str): ID del usuario que interactúa con el agente.
        req (ChatTurnRequest): Objeto con detalles del turno/mensaje y contexto.
        max_round_trips_override (int, opcional): Número máximo de rondas para la conversación (override de setting).
        record_history (bool, opcional): Si True, registra el historial de mensajes/conversación.
        load_session_history (bool, opcional): Cargar historial PG. None = igual a record_history.
        delegation_depth (int, opcional): 0 user-facing; incrementa en cada delegate.

    Yields:
        Dict[str, Any]: Diccionario con eventos de tipo:
            - {"type": "status", "message": ...}
            - {"type": "delegation_start", ...}
            - {"type": "delegation_end", ...}
            - {"type": "done", "reply": ..., "affected_resources": [...]}
            - {"type": "error", "message": ...}

    Raises:
        BedrockError: Si ocurre un error durante la ejecución de la ronda conversacional (emite evento de error).
    """
    # 1. Cargar configuración de runtime y verificar presupuesto de usuario
    runtime = await settings_loader.get_runtime_settings(db)
    await budget.assert_budget_available(db, user_id, runtime.daily_budget_usd)

    # 2. Resolver perfil de agente y modelo a usar
    from services.section_catalog import resolve_profile_for_turn

    profile = await resolve_profile_for_turn(
        db,
        chat_surface=req.chat_surface,
        agent_profile_id=req.agent_profile_id,
        page_context=req.page_context,
    )
    if profile.level == 3 and record_history:
        yield {
            "type": "error",
            "message": "Los agentes de nivel 3 no tienen chat con el usuario. Delega desde L1 o L2.",
        }
        return
    from services.bedrock import profile_delegation

    allowed_delegate_ids = await profile_delegation.get_effective_delegation_ids(db, profile)
    model_id = _effective_model(req, runtime, profile)
    system_prompt = await prompt.compose_system_prompt(
        db, profile, req.page_context, user_id=user_id, delegate_ids=allowed_delegate_ids
    )

    # 3. Determinar herramientas permitidas para el perfil, y construir especificaciones de herramientas
    allowed = agent_profiles.tools_for_profile(profile, tools.all_tool_names())
    tool_specs = tools.converse_tool_specs(
        allowed, caller_profile=profile, delegate_ids=allowed_delegate_ids
    )

    # 4. Determinar tipo de sesión y cargar historial de conversación
    session_type = "general" if req.chat_surface == "general" else "contextual"
    conversation = None
    include_history = record_history if load_session_history is None else load_session_history
    if include_history:
        history = await history_manager.load_converse_messages(db, user_id, req.session_id, runtime.history_window)
    else:
        history = []
    user_content = await build_user_content_blocks(db, user_id, req.message, req.attachments)
    messages = history + [{"role": "user", "content": user_content}]

    # 5. Registrar o crear la conversación en la base de datos si corresponde
    if record_history:
        conversation = await history_manager.get_or_create_conversation(
            db,
            user_id,
            req.session_id,
            req.message,
            session_type=session_type,
            agent_profile_id=profile.id,
        )

    # 6. Inicializar variables para recursos afectados, control de uso de tokens, rondas y delegaciones
    affected: List[str] = []
    total_usage = {
        "inputTokens": 0,
        "outputTokens": 0,
        "cacheReadInputTokens": 0,
        "cacheWriteInputTokens": 0,
    }
    max_rounds = max_round_trips_override or runtime.max_round_trips
    delegations_used = 0
    persist_nudge_sent = False
    # Lecturas ya resueltas en este turno: (tool, input) -> resultado ya enviado
    # arriba. Evita reincrustar el mismo registro grande ronda tras ronda.
    seen_reads: set = set()

    # 7. Emitir un evento de status inicial ("Pensando...")
    yield {"type": "status", "message": "Pensando..."}

    # 8. Loop principal de rondas de conversación
    force_tool_this_round = True
    for _ in range(max_rounds):
        try:
            # 8.1. Invocar al cliente converse con el modelo y el historial de mensajes actual
            result = await converse_client.converse(
                model_id=model_id,
                messages=messages,
                system_prompt=system_prompt,
                tools=tool_specs,
                force_tool_use=force_tool_this_round and bool(tool_specs),
            )
        except BedrockError as e:
            # 8.2. Si hubo un error de Bedrock, registra lo ya gastado en rondas
            # previas de este turno (incluida la escritura de caché) y termina.
            if any(total_usage.values()):
                await usage_logger.record_turn_usage(user_id, req.session_id, model_id, total_usage)
            yield {"type": "error", "message": str(e)}
            return
        force_tool_this_round = False

        # 8.3. Acumular tokens consumidos (input/output/caché) y loggear el uso de la ronda
        total_usage["inputTokens"] += result["usage"]["inputTokens"]
        total_usage["outputTokens"] += result["usage"]["outputTokens"]
        total_usage["cacheReadInputTokens"] += result["usage"].get("cacheReadInputTokens", 0)
        total_usage["cacheWriteInputTokens"] += result["usage"].get("cacheWriteInputTokens", 0)
        await usage_logger.record_round_log(
            user_id=user_id,
            session_id=req.session_id,
            model_id=model_id,
            round_type="converse",
            usage=result["usage"],
            agent_profile_id=profile.id,
        )

        # 9. Si el modelo NO requiere uso de herramientas (ya tiene respuesta final)
        if result["stop_reason"] != "tool_use":
            if should_nudge_persist(
                profile.id, req.message, affected, persist_nudge_sent, result.get("text") or ""
            ):
                persist_nudge_sent = True
                force_tool_this_round = True
                yield {"type": "status", "message": "Persistiendo el contenido en la base de datos..."}
                assistant_blocks: List[Dict[str, Any]] = []
                if result["text"]:
                    assistant_blocks.append({"text": result["text"]})
                if not assistant_blocks:
                    assistant_blocks.append({"text": "(sin texto)"})
                messages.extend(
                    [
                        {"role": "assistant", "content": assistant_blocks},
                        {"role": "user", "content": [{"text": persist_nudge_text(profile.id)}]},
                    ]
                )
                continue
            # 9.1. Loggear uso total de la vuelta
            await usage_logger.record_turn_usage(user_id, req.session_id, model_id, total_usage)
            # Bedrock Converse rechaza bloques de texto vacíos: si el modelo terminó sin
            # texto (p.ej. una respuesta que fue enteramente <thinking>), usamos un
            # placeholder para que el historial persistido siga siendo válido en el
            # siguiente turno.
            final_reply = result["text"] or "(sin texto)"
            # 9.2. Registrar mensajes en historial si corresponde
            if record_history and conversation:
                await history_manager.append_message(db, conversation, "user", req.message or "(sin texto)")
                await history_manager.append_message(db, conversation, "assistant", final_reply)
            # 9.3. Emitir evento "done" con respuesta final y los recursos afectados
            yield {"type": "done", "reply": final_reply, "affected_resources": affected}
            return

        # 10. Si el modelo requiere ejecución de herramientas
        # 10.1. Emitir eventos de status por cada herramienta a usar
        for t in result["tool_uses"]:
            yield {"type": "status", "message": _TOOL_STATUS.get(t["name"], f"Usando {t['name']}...")}

        # 10.2. Preparar contenido para mensajes siguientes (contenido de herramientas usadas)
        assistant_content = [
            {"toolUse": {"toolUseId": t["toolUseId"], "name": t["name"], "input": t["input"]}}
            for t in result["tool_uses"]
        ]
        tool_result_content = []

        # 10.3. Ejecutar cada herramienta solicitada y recopilar sus resultados
        for t in result["tool_uses"]:
            name = t["name"]
            try:
                status = "success"
                # 10.3.1. Si la herramienta es "delegate_to_specialist" (delegación a especialista)
                if name == "delegate_to_specialist":
                    spec_id = t["input"].get("agent_profile_id", "")
                    deny = None
                    if not profile.can_delegate:
                        deny = "this profile cannot delegate"
                    elif delegation_depth >= 2:
                        deny = "max delegation depth exceeded"
                    elif delegations_used >= settings.BEDROCK_MAX_DELEGATIONS_PER_TURN:
                        deny = "max delegations per turn exceeded"
                    else:
                        deny = agent_profiles.delegation_error(
                            profile, spec_id, allowed_ids=set(allowed_delegate_ids)
                        )
                    if deny:
                        tool_result = {"error": deny}
                        status = "error"
                    else:
                        try:
                            target = agent_profiles.get_profile(spec_id)
                        except KeyError:
                            tool_result = {"error": f"unknown agent profile: {spec_id}"}
                            status = "error"
                        else:
                            yield {
                                "type": "delegation_start",
                                "agent_profile_id": spec_id,
                                "label": target.label,
                                "level": target.level,
                                "task_preview": (t["input"].get("task") or "")[:120],
                            }
                            sub = await run_specialist_sub_turn(
                                db,
                                user_id=user_id,
                                session_id=req.session_id,
                                profile=target,
                                task=t["input"].get("task", ""),
                                context=t["input"].get("context"),
                                delegation_depth=delegation_depth,
                            )
                            delegations_used += 1
                            tool_result = sub
                            yield {
                                "type": "delegation_end",
                                "agent_profile_id": spec_id,
                                "success": True,
                                "summary_preview": sub.get("summary", "")[:200],
                            }
                else:
                    # 10.3.2. Ejecución de herramientas normales
                    dedup_key = (
                        f"{name}:{json.dumps(t['input'], sort_keys=True, ensure_ascii=False)}"
                        if name in _DEDUP_READ_TOOLS
                        else None
                    )
                    if t.get("input_parse_error"):
                        tool_result = {"error": t["input_parse_error"]}
                        status = "error"
                    elif dedup_key is not None and dedup_key in seen_reads:
                        # Lectura idéntica ya devuelta en este turno: no reejecutar
                        # ni reincrustar el payload (ahorro de tokens de entrada).
                        tool_result = {
                            "note": (
                                "Idéntico a una llamada previa en este mismo turno. "
                                "Reutiliza aquel resultado; no lo vuelvas a pedir."
                            )
                        }
                        status = "success"
                    else:
                        tool_result = await tools.execute_tool(
                            db, user_id, name, t["input"], req.session_id, caller_profile_id=profile.id
                        )
                        status = "success"
                        if dedup_key is not None:
                            seen_reads.add(dedup_key)
                # 10.3.3. Registrar recursos afectados por la delegación si es el caso
                if name == "delegate_to_specialist" and isinstance(tool_result, dict):
                    for key in tool_result.get("affected_resources") or []:
                        if key not in affected:
                            affected.append(key)
                # 10.3.4. Determinar clave de invalidación de recursos y registrar si es necesario
                inv_key = tools.invalidation_key(name, t["input"], tool_result)
                if inv_key and inv_key not in affected:
                    affected.append(inv_key)
                # 10.3.4b. Un write (directo o vía delegación) invalida las lecturas
                # deduplicadas de este turno: una relectura posterior debe ver el
                # estado nuevo, no el snapshot previo a la escritura.
                _wrote = (
                    tools.is_write_tool(name)
                    and not (isinstance(tool_result, dict) and tool_result.get("error"))
                ) or (
                    name == "delegate_to_specialist"
                    and isinstance(tool_result, dict)
                    and tool_result.get("affected_resources")
                )
                if _wrote:
                    seen_reads.clear()
            except Exception as e:
                # 10.3.5. Si ocurre un error al ejecutar la herramienta.
                # Crítico: un fallo de flush (p.ej. IntegrityError por un NOT
                # NULL) deja la sesión en "pending rollback" - sin este
                # rollback, cualquier tool de escritura posterior EN ESTE
                # MISMO TURNO (rondas siguientes, incluido el registro de
                # auditoría) revienta con un PendingRollbackError genérico
                # que oculta la causa real. db.rollback() es seguro de
                # llamar aunque el error no haya sido de base de datos.
                try:
                    await db.rollback()
                except Exception:
                    logger.exception("db.rollback() falló tras error en tool %s", name)

                from services.error_reporting import report_error

                report_error(
                    str(e) or f"Fallo al ejecutar la tool {name}",
                    f"bedrock:tool.{name}",
                    error_type=type(e).__name__,
                    exc=e,
                    context={"session_id": req.session_id, "agent_profile_id": profile.id},
                    severity="error",
                )
                tool_result = {"error": str(e)}
                status = "error"

            # 10.3.6. Acumular resultado de la herramienta para el mensaje siguiente
            tool_result_content.append({
                "toolResult": {
                    "toolUseId": t["toolUseId"],
                    "content": [{"text": json.dumps(tool_result, ensure_ascii=False, default=str)}],
                    "status": status,
                }
            })

        # 10.4. Agregar los resultados de la ronda al historial de mensajes para la próxima interacción
        messages.extend([
            {"role": "assistant", "content": assistant_content},
            {"role": "user", "content": tool_result_content},
        ])

    # 11. Si se agotaron las vueltas sin obtener respuesta final, registrar el uso y emitir un error final
    await usage_logger.record_turn_usage(user_id, req.session_id, model_id, total_usage)
    yield {"type": "error", "message": "Se agotaron las vueltas del agente sin respuesta final."}
