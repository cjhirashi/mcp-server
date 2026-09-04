"""
Agent Bedrock — fachada del asistente IA del Admin Panel.

El loop de chat vive en `services/bedrock/` (Harness local Converse API).
Este módulo conserva herramientas CRUD, bitácora, conversaciones PG y
embeddings Titan usados por el harness y por CareerRepository.
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import boto3

from config import settings
from repositories.career_repository import CareerRepository
from routes.career_common import RESOURCE_REGISTRY
from services import qdrant_service

logger = logging.getLogger(__name__)


class BedrockError(Exception):
    """Raised for any Bedrock/agent failure - callers turn this into an HTTP error."""


# ---------------------------------------------------------------------------
# AWS — cliente bedrock-runtime solo para Titan Embeddings (embed_text).
# El chat Converse vive en services/bedrock/converse_client.py.
# ---------------------------------------------------------------------------

_embedding_client = None
_repositories: Dict[str, CareerRepository] = {}


def _require_configured() -> None:
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise BedrockError("Bedrock is not configured (missing AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)")


def _get_embedding_client():
    """`bedrock-runtime` client, used only for Titan Embeddings - the
    knowledge base embeds text directly, outside of the harness."""
    global _embedding_client
    _require_configured()
    if _embedding_client is None:
        _embedding_client = boto3.client(
            "bedrock-runtime",
            region_name=settings.BEDROCK_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
    return _embedding_client


def _get_repository(resource_key: str) -> CareerRepository:
    """Una instancia de `CareerRepository` por recurso, reutilizada entre
    llamadas (es barato de construir, pero no hay razón para reconstruirlo
    en cada llamada a herramienta). Es exactamente la misma clase de
    repositorio que ya usa cada ruta CRUD genérica `/career/{key}` - las
    herramientas del agente de más abajo no reimplementan el acceso a
    datos, solo llaman a esto."""
    if resource_key not in RESOURCE_REGISTRY:
        raise BedrockError(f"Unknown resource_key: {resource_key}")
    if resource_key not in _repositories:
        _repositories[resource_key] = CareerRepository(RESOURCE_REGISTRY[resource_key], resource_key=resource_key)
    return _repositories[resource_key]


async def embed_text(text: str) -> List[float]:
    """Embed `text` with Bedrock Titan Embeddings. Runs boto3's sync call in
    a thread since boto3 has no native async support."""
    client = _get_embedding_client()

    def _invoke():
        response = client.invoke_model(
            modelId=settings.BEDROCK_EMBEDDING_MODEL_ID,
            body=json.dumps({"inputText": text}),
        )
        return json.loads(response["body"].read())

    try:
        result = await asyncio.to_thread(_invoke)
    except Exception as e:
        raise BedrockError(f"Embedding request failed: {e}") from e
    return result["embedding"]


# ---------------------------------------------------------------------------
# Cambio de modelo
# ---------------------------------------------------------------------------

async def get_current_model() -> str:
    """Modelo activo del chat — persistido en bedrock_settings (PostgreSQL)."""
    from services.bedrock.settings_loader import get_active_model_id
    from database import AsyncSessionLocal

    _require_configured()
    async with AsyncSessionLocal() as db:
        return await get_active_model_id(db)


async def switch_model(model_id: str) -> None:
    """Cambia el modelo activo del chat (persiste en bedrock_settings)."""
    if model_id not in settings.BEDROCK_AVAILABLE_MODELS:
        raise BedrockError(f"Model not in the allow-list: {model_id}")

    from services.bedrock.settings_loader import set_active_model_id
    from database import AsyncSessionLocal

    _require_configured()
    async with AsyncSessionLocal() as db:
        await set_active_model_id(db, model_id)


# ---------------------------------------------------------------------------
# Tool execution — schemas Converse en services/bedrock/tools.py; ejecución
# CRUD en `_execute_tool` más abajo. MCP custom tools: CRUD en este módulo.
# ---------------------------------------------------------------------------



async def list_custom_tools(db) -> List["BedrockCustomTool"]:  # noqa: F821 - imported below for the type only
    from sqlalchemy import select

    from models.bedrock_custom_tool import BedrockCustomTool

    result = await db.execute(select(BedrockCustomTool).order_by(BedrockCustomTool.created_at.desc()))
    return result.scalars().all()


async def create_custom_tool(db, name: str, url: str, headers: Optional[Dict[str, str]] = None) -> "BedrockCustomTool":  # noqa: F821
    from models.bedrock_custom_tool import BedrockCustomTool

    tool = BedrockCustomTool(name=name, url=url, headers=headers or None, is_enabled=True)
    db.add(tool)
    await db.flush()
    await db.refresh(tool)
    await db.commit()
    return tool


async def set_custom_tool_enabled(db, tool_id: str, is_enabled: bool) -> Optional["BedrockCustomTool"]:  # noqa: F821
    from sqlalchemy import select

    from models.bedrock_custom_tool import BedrockCustomTool

    result = await db.execute(select(BedrockCustomTool).where(BedrockCustomTool.id == tool_id))
    tool = result.scalar_one_or_none()
    if tool is None:
        return None
    tool.is_enabled = is_enabled
    await db.commit()
    await db.refresh(tool)
    return tool


async def delete_custom_tool(db, tool_id: str) -> bool:
    from sqlalchemy import select

    from models.bedrock_custom_tool import BedrockCustomTool

    result = await db.execute(select(BedrockCustomTool).where(BedrockCustomTool.id == tool_id))
    tool = result.scalar_one_or_none()
    if tool is None:
        return False
    await db.delete(tool)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Motor de ejecución de herramientas - `_execute_tool` es el despachador que
# `chat_stream` llama cada vez que el harness se pausa con
# `stop_reason == "tool_use"` (cada herramienta `inline_function` definida
# arriba corresponde a un `if` aquí, según su nombre). Todo esto corre
# LOCALMENTE, en este proceso - el harness nunca toca la base de datos ni
# Qdrant directamente, solo decide *qué* herramienta llamar y *con qué
# argumentos*; esta función es la que realmente hace el trabajo y devuelve
# el resultado.
# ---------------------------------------------------------------------------


def _serialize(obj: Any) -> Dict[str, Any]:
    """SQLAlchemy row -> plain dict of its real columns, JSON-safe (dates,
    Decimals, enums, etc. get stringified before going back to the model)."""
    from sqlalchemy import inspect as sa_inspect

    if obj is None:
        return {}
    result: Dict[str, Any] = {}
    for attr in sa_inspect(obj).mapper.column_attrs:
        value = getattr(obj, attr.key)
        result[attr.key] = value if isinstance(value, (dict, list, int, float, bool, str)) or value is None else str(value)
    return result


_LIST_LABEL_FIELDS = ("title", "name", "company", "exact_role", "role_name", "tag_name", "slug")
_LIST_SUMMARY_FIELDS = ("context", "challenge", "status", "evaluation", "card_summary", "excerpt")


def _serialize_list_item(obj: Any, extra_fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """Vista compacta para listados — evita truncar resultados grandes.

    extra_fields agrega columnas puntuales (ej. `nivel`) a cada item de la
    lista. Sin esto, revisar un campo en todos los registros de un recurso
    forzaba al agente a un get_career_record por fila — 69 llamadas para
    revisar 69 competencias, suficiente para agotar max_round_trips antes de
    llegar siquiera a escribir nada (regresión real, ver bulk_update_career_record
    y should_retry_max_tokens: ninguno de los dos ayuda si el cuello de botella
    es de lecturas, no de escrituras ni de tokens)."""
    full = _serialize(obj)
    item: Dict[str, Any] = {"id": full.get("id")}
    for field in _LIST_LABEL_FIELDS:
        value = full.get(field)
        if value:
            item["title"] = str(value)
            break
    for field in _LIST_SUMMARY_FIELDS:
        value = full.get(field)
        if value and isinstance(value, str):
            text = value.strip()
            if text:
                item["summary"] = text[:240] + ("…" if len(text) > 240 else "")
                break
    if extra_fields:
        for field in extra_fields:
            if field in full and field not in item:
                item[field] = full[field]
    return item


def _normalize_record_id(resource_key: str, record_id: Any) -> str:
    """Convierte record_id al formato prefijado (ej. 17 → ach-17 si resource_key=achievements)."""
    from services.id_generator import normalize_prefixed_id

    return normalize_prefixed_id(resource_key, record_id)


async def _record_audit(
    db,
    *,
    user_id: str,
    action: str,
    resource_key: str,
    record_id: Optional[str],
    old_values: Optional[Dict[str, Any]],
    new_values: Optional[Dict[str, Any]],
    session_id: str,
) -> None:
    """Every write the agent makes, logged with the full before/after record
    state - specifically so a mistaken delete is recoverable (old_values has
    the complete row, not just its id). Not best-effort like the Qdrant
    indexing hook: an audit trail that can silently fail to record a delete
    defeats its own purpose, so a failure here raises and the caller
    (chat_stream) surfaces it as a tool error rather than pretending the
    write was clean."""
    from models.audit_log import AuditAction, AuditLog

    db.add(
        AuditLog(
            user_id=user_id,
            action=AuditAction(action),
            resource_type=resource_key,
            resource_id=record_id,
            old_values=old_values,
            new_values=new_values,
            reason="Agent Bedrock",
            extra_metadata={"session_id": session_id},
        )
    )
    await db.commit()


async def _execute_tool(
    db,
    user_id: str,
    name: str,
    tool_input: Dict[str, Any],
    session_id: str,
    caller_profile_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one tool call, scoped to `user_id` throughout - same isolation
    guarantee as every other authenticated route in this API."""
    if name == "search_knowledge_base":
        from services.methodology_scope import applies_to_agent

        vector = await embed_text(tool_input["query"])
        resource_type = tool_input.get("type")
        top_k = tool_input.get("top_k", 5)
        fetch_k = top_k * 3 if resource_type == "methodology" else top_k
        results = await qdrant_service.search(
            user_id=user_id,
            vector=vector,
            top_k=fetch_k,
            resource_type=resource_type,
        )
        if resource_type == "methodology":
            results = [
                row
                for row in results
                if applies_to_agent(row.get("agent_profile_ids"), caller_profile_id)
            ][:top_k]
        return {"results": results}

    if name == "list_career_record":
        repo = _get_repository(tool_input["resource_key"])
        skip = tool_input.get("skip", 0)
        limit = min(tool_input.get("limit", 20), 100)
        items = await repo.list_for_user(
            db,
            user_id,
            skip=skip,
            limit=limit,
            sort_by=tool_input.get("sort_by"),
            sort_dir=tool_input.get("sort_dir", "asc"),
            search=tool_input.get("search"),
        )
        total_count = await repo.count_for_user(db, user_id)
        extra_fields = tool_input.get("fields")
        serialized = [_serialize_list_item(item, extra_fields) for item in items]
        return {
            "items": serialized,
            "total_count": total_count,
            "returned_count": len(serialized),
            "skip": skip,
            "has_more": skip + len(serialized) < total_count,
            "instruction": (
                "Menciona TODOS los items de esta respuesta. "
                "Si has_more es true, llama de nuevo con skip=skip+returned_count hasta agotar."
            ),
        }

    if name == "count_career_records":
        repo = _get_repository(tool_input["resource_key"])
        search = tool_input.get("search")
        if search:
            items = await repo.list_for_user(db, user_id, skip=0, limit=100, search=search)
            count = len(items)
        else:
            count = await repo.count_for_user(db, user_id)
        return {
            "count": count,
            "resource_key": tool_input["resource_key"],
            "instruction": "Responde con este número exacto. Para listar nombres usa list_career_record.",
        }

    if name == "get_career_record":
        repo = _get_repository(tool_input["resource_key"])
        record_id = _normalize_record_id(tool_input["resource_key"], tool_input["record_id"])
        item = await repo.get_for_user(db, user_id, record_id)
        if item is None:
            return {"error": "not_found"}
        data = _serialize(item)
        fields = tool_input.get("fields")
        if fields:
            keep = {str(f) for f in fields} | {"id"}
            data = {k: v for k, v in data.items() if k in keep}
        return {"item": data}

    if name == "describe_resource_schema":
        repo = _get_repository(tool_input["resource_key"])
        return {
            "fields": sorted(repo._indexable_columns),
            "required_fields": list(repo._required_columns),
            "instruction": (
                "required_fields son NOT NULL sin default: create_career_record los "
                "necesita todos o Postgres rechaza el insert."
            ),
        }

    if name == "list_recent_changes":
        entries = await list_audit_log(db, user_id, limit=min(tool_input.get("limit", 10), 50))
        resource_filter = tool_input.get("resource_key")
        if resource_filter:
            entries = [e for e in entries if e.resource_type == resource_filter]
        return {
            "entries": [
                {
                    "audit_id": e.id,
                    "action": e.action.value,
                    "resource_key": e.resource_type,
                    "record_id": e.resource_id,
                    "created_at": str(e.created_at),
                }
                for e in entries
            ]
        }

    if name == "restore_deleted_record":
        try:
            restored = await restore_audit_entry(db, user_id, tool_input["audit_id"])
        except BedrockError as e:
            return {"error": str(e)}
        return {"item": restored}

    if name == "create_career_record":
        resource_key = tool_input["resource_key"]
        repo = _get_repository(resource_key)
        invalid = _invalid_fields_error(repo, tool_input["fields"], require_all=True)
        if invalid:
            return invalid
        item = await repo.create_for_user(db, user_id, tool_input["fields"])
        serialized = _serialize(item)
        await _record_audit(
            db,
            user_id=user_id,
            action="create",
            resource_key=resource_key,
            record_id=item.id,
            old_values=None,
            new_values=serialized,
            session_id=session_id,
        )
        return {"item": serialized}

    if name == "update_career_record":
        resource_key = tool_input["resource_key"]
        repo = _get_repository(resource_key)
        invalid = _invalid_fields_error(repo, tool_input["fields"])
        if invalid:
            return invalid
        record_id = _normalize_record_id(resource_key, tool_input["record_id"])
        before = await repo.get_for_user(db, user_id, record_id)
        if before is None:
            return {"error": "not_found"}
        before_serialized = _serialize(before)
        item = await repo.update_for_user(db, user_id, record_id, tool_input["fields"])
        serialized = _serialize(item)
        await _record_audit(
            db,
            user_id=user_id,
            action="update",
            resource_key=resource_key,
            record_id=item.id,
            old_values=before_serialized,
            new_values=serialized,
            session_id=session_id,
        )
        return {"item": serialized}

    if name == "delete_career_record":
        resource_key = tool_input["resource_key"]
        repo = _get_repository(resource_key)
        record_id = _normalize_record_id(resource_key, tool_input["record_id"])
        # Captured BEFORE the delete - this is the row the audit log exists
        # to preserve. Without it, a mistaken delete is unrecoverable (this
        # feature exists precisely because that already happened once).
        before = await repo.get_for_user(db, user_id, record_id)
        if before is None:
            return {"deleted": False}
        before_serialized = _serialize(before)
        deleted = await repo.delete_for_user(db, user_id, record_id)
        if deleted:
            await _record_audit(
                db,
                user_id=user_id,
                action="delete",
                resource_key=resource_key,
                record_id=record_id,
                old_values=before_serialized,
                new_values=None,
                session_id=session_id,
            )
        return {"deleted": deleted}

    raise BedrockError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Bitácora (audit log) - lectura + restauración. La escritura pasa en
# _execute_tool/_record_audit más arriba; esto es el lado de Carlos (la
# página Bitácora).
# ---------------------------------------------------------------------------

async def list_audit_log(db, user_id: str, limit: int = 50, offset: int = 0) -> List["AuditLog"]:  # noqa: F821
    from sqlalchemy import select

    from models.audit_log import AuditLog

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == user_id, AuditLog.reason == "Agent Bedrock")
        .order_by(AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


async def restore_audit_entry(db, user_id: str, audit_id: str) -> Dict[str, Any]:
    """Deshace un delete que hizo el agente: recrea el registro a partir de
    `old_values` de la entrada de bitácora (la fila completa capturada
    justo antes del delete). Solo tiene sentido para entradas `delete` - un
    create/update no tiene a qué "restaurarse" que no sea ya la fila
    actual."""
    from sqlalchemy import select

    from models.audit_log import AuditLog

    result = await db.execute(select(AuditLog).where(AuditLog.id == audit_id, AuditLog.user_id == user_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise BedrockError("Audit log entry not found")
    if entry.action.value != "delete" or not entry.old_values:
        raise BedrockError("Only a 'delete' entry with saved old_values can be restored")

    repo = _get_repository(entry.resource_type)
    # Drop columns the DB assigns itself - re-inserting the exact old id
    # isn't guaranteed possible (a new row may already have reused it) and
    # timestamps should reflect the restore, not the original creation.
    fields = {k: v for k, v in entry.old_values.items() if k not in ("id", "user_id", "created_at", "updated_at")}
    item = await repo.create_for_user(db, user_id, fields)
    serialized = _serialize(item)
    await _record_audit(
        db,
        user_id=user_id,
        action="create",
        resource_key=entry.resource_type,
        record_id=item.id,
        old_values=None,
        new_values=serialized,
        session_id="restore-from-audit-log",
    )
    return serialized


def _invalid_fields_error(
    repo: CareerRepository, fields: Dict[str, Any], require_all: bool = False
) -> Optional[Dict[str, Any]]:
    """Reject unknown column names (and, on create, missing NOT NULL ones)
    before they ever reach SQLAlchemy, with the real column list in the
    error - without this, a wrong guess (e.g. `name` instead of `tag_name`)
    surfaces as a generic ORM TypeError that tells the model nothing about
    what the right field is, burning an extra search_knowledge_base + retry
    round-trip (measured: 4-6 tool calls for what should take 1-2) just to
    rediscover the schema by trial and error.

    A missing NOT NULL field is worse than a wrong name: instead of a clean
    ORM error it flushes as a raw asyncpg IntegrityError, and - see
    agent_loop's tool exception handler - that leaves the session's
    transaction unrolled-back for the rest of the turn, so every write
    after it fails with an opaque "Session's transaction has been rolled
    back" instead of the real cause. require_all=True (create only) catches
    it before the flush ever happens."""
    valid = set(repo._indexable_columns)
    unknown = sorted(set(fields.keys()) - valid)
    if unknown:
        return {
            "error": f"Unknown field(s) {unknown} for this resource.",
            "valid_fields": sorted(valid),
        }
    if require_all:
        missing = sorted(col for col in repo._required_columns if fields.get(col) is None)
        if missing:
            return {
                "error": f"Missing required field(s) {missing} for this resource (NOT NULL, sin default).",
                "required_fields": list(repo._required_columns),
            }
    return None


# ---------------------------------------------------------------------------
# System prompt — se compone en cada turno Converse (ver agent_loop.chat_stream).
# Carlos puede editarlo vía /bedrock/instructions; aplica en el siguiente mensaje.
# ---------------------------------------------------------------------------


def default_system_prompt() -> str:
    resource_list = ", ".join(sorted(RESOURCE_REGISTRY.keys()))
    return (
        "Eres el asistente de carrera dentro del Admin Panel de Carlos Jiménez Hirashi. "
        "Tienes acceso completo de lectura y escritura sobre sus datos de carrera a través de tus "
        "herramientas - puedes listar, obtener, crear, actualizar y eliminar registros directamente, "
        "sin pedir confirmación adicional del sistema (Carlos ya te la dio al usarte). "
        "Redactar el contenido en el chat no lo persiste: debes llamar las tools de escritura "
        "en el mismo turno; no afirmes que guardaste hasta que la tool devuelva el id. "
        "Antes de operar una tabla que no conozcas bien, usa search_knowledge_base (type=methodology) "
        "para consultar SOLO las metodologías operativas asignadas a tu perfil "
        "(campo Agentes / agent_profile_ids) más las compartidas (lista vacía). "
        "Ahí está documentado cómo se relacionan las tablas y qué disciplina seguir. "
        "Una metodología nueva que Carlos te asigne desde el Admin es tuya de inmediato: consúltala; "
        "no esperes que el código la nombre. No apliques metodologías de otros agentes. "
        "Mantener el texto de las metodologías (crear/editar operational-methodologies) es del "
        "guardián agent_methodologies, salvo que Carlos te pida lo contrario. "
        "Antes de crear un registro en un recurso cuyos campos exactos no tengas ya confirmados (por un "
        "list_career_record o get_career_record previo en esta misma conversación), llama primero a "
        "describe_resource_schema - los nombres de columna reales no siempre son los que se adivinarían "
        "(ej. 'tags' usa tag_name/entity_type, no name/category). Evita adivinar campos a ciegas. "
        "Con registros grandes (p.ej. projects) llama get_career_record con 'fields' limitado a las "
        "columnas que vas a leer o editar; no traigas el registro completo para tocar 1-2 campos. "
        "Para una petición de varios pasos (ej. 'actualiza toda mi sección de Identidad' o cualquier tarea "
        "que tome más de 2-3 llamadas a herramientas), usa el resource_key 'agent-tasks' (fields: title, "
        "description, status) para planear primero: crea una tarea por paso con status='pending', y ve "
        "actualizando cada una a 'in_progress' antes de ejecutarla y a 'done' al terminarla (o "
        "'cancelled' si ya no aplica) - así Carlos puede ver el plan avanzar, y tú puedes retomarlo en "
        "otra conversación si esta se corta a la mitad. Para un mensaje simple de un solo paso, no hace "
        "falta crear una tarea. "
        "Cada create/update/delete que haces queda registrado automáticamente en la bitácora, con el "
        "estado completo del registro antes y después - no necesitas escribir nada ahí tú mismo. Usa "
        "list_recent_changes si Carlos pregunta qué hiciste, o si necesitas confirmar un cambio antes de "
        "seguir. Si Carlos te pide deshacer algo que eliminaste (en esta conversación o una anterior), "
        "usa list_recent_changes para encontrar el audit_id de esa eliminación y luego "
        "restore_deleted_record - no lo recrees a mano con create_career_record, el registro restaurado "
        "debe salir exactamente del estado que guardó la bitácora. "
        "Responde siempre en español, de forma clara y directa sobre qué hiciste. "
        "No envuelvas la respuesta al usuario en etiquetas de razonamiento interno "
        "(<thinking>, </thinking>, <think>, </think>). "
        f"Recursos disponibles (resource_key): {resource_list}."
    )


async def get_system_prompt(db) -> str:
    """The active system prompt - Carlos's override if he's set one (see
    /bedrock/instructions), otherwise the built-in default. Read fresh on
    every turn (see chat_stream) rather than cached, so an edit takes effect
    on the very next message."""
    from sqlalchemy import select

    from models.bedrock_settings import BedrockSettings

    result = await db.execute(select(BedrockSettings).limit(1))
    row = result.scalar_one_or_none()
    if row and row.system_prompt:
        return row.system_prompt
    return default_system_prompt()


async def set_system_prompt(db, text: Optional[str]) -> str:
    """Set (or, with `text=None`, clear) the override. Returns the resulting
    active prompt. Single-row table (`BedrockSettings` is a single-operator
    setting, not per-user) - creates the row on first use."""
    from sqlalchemy import select

    from models.bedrock_settings import BedrockSettings

    result = await db.execute(select(BedrockSettings).limit(1))
    row = result.scalar_one_or_none()
    if row is None:
        row = BedrockSettings(system_prompt=text)
        db.add(row)
    else:
        row.system_prompt = text
    await db.commit()
    return await get_system_prompt(db)


def default_global_rules() -> str:
    """The built-in global rules (grounding + methodology assignment) that
    apply to every agent regardless of level/profile."""
    from services.bedrock.prompt import default_global_rules as _default_global_rules

    return _default_global_rules()


async def get_global_rules(db) -> str:
    """The active global rules - Carlos's override if he's set one (see
    /bedrock/global-rules), otherwise the built-in default. Read fresh on
    every turn (see compose_system_prompt) rather than cached, so an edit
    takes effect on the very next message."""
    from sqlalchemy import select

    from models.bedrock_settings import BedrockSettings

    result = await db.execute(select(BedrockSettings).limit(1))
    row = result.scalar_one_or_none()
    if row and row.global_rules:
        return row.global_rules
    return default_global_rules()


async def set_global_rules(db, text: Optional[str]) -> str:
    """Set (or, with `text=None`, clear) the override. Returns the resulting
    active global rules. Single-row table (`BedrockSettings` is a
    single-operator setting, not per-user) - creates the row on first use."""
    from sqlalchemy import select

    from models.bedrock_settings import BedrockSettings

    result = await db.execute(select(BedrockSettings).limit(1))
    row = result.scalar_one_or_none()
    if row is None:
        row = BedrockSettings(global_rules=text)
        db.add(row)
    else:
        row.global_rules = text
    await db.commit()
    return await get_global_rules(db)


# ---------------------------------------------------------------------------
# Conversaciones — historial en PostgreSQL (history_manager + endpoints /bedrock/conversations).
# ---------------------------------------------------------------------------

async def list_conversations(db, user_id: str) -> List["BedrockConversation"]:  # noqa: F821
    from sqlalchemy import select

    from models.bedrock_conversation import BedrockConversation

    result = await db.execute(
        select(BedrockConversation)
        .where(BedrockConversation.user_id == user_id)
        .order_by(BedrockConversation.updated_at.desc())
    )
    return result.scalars().all()


async def get_conversation_messages(db, user_id: str, session_id: str) -> List["BedrockConversationMessage"]:  # noqa: F821
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from models.bedrock_conversation import BedrockConversation

    result = await db.execute(
        select(BedrockConversation)
        .options(selectinload(BedrockConversation.messages))
        .where(BedrockConversation.session_id == session_id, BedrockConversation.user_id == user_id)
    )
    conversation = result.scalar_one_or_none()
    return conversation.messages if conversation else []


async def rename_conversation(db, user_id: str, session_id: str, title: str) -> bool:
    from sqlalchemy import select

    from models.bedrock_conversation import BedrockConversation

    result = await db.execute(
        select(BedrockConversation).where(
            BedrockConversation.session_id == session_id, BedrockConversation.user_id == user_id
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return False
    conversation.title = title[:255]
    await db.commit()
    return True


async def delete_conversation(db, user_id: str, session_id: str) -> bool:
    from sqlalchemy import select

    from models.bedrock_conversation import BedrockConversation

    result = await db.execute(
        select(BedrockConversation).where(
            BedrockConversation.session_id == session_id, BedrockConversation.user_id == user_id
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return False
    await db.delete(conversation)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Chat — delega en services/bedrock/agent_loop.py (Converse API + tools).
# ---------------------------------------------------------------------------


async def chat(db, user_id: str, session_id: str, message: str) -> Dict[str, Any]:
    """Run one chat turn against the harness. The harness owns the
    conversation history server-side (keyed by `session_id`) - callers only
    ever send the newest user message, never the full history.

    Returns `{"reply": str, "affected_resources": list[str]}` -
    `affected_resources` lists every resource_key touched by a write tool
    this turn, so the frontend can invalidate its cache for those tables.

    Thin wrapper around `chat_stream` for callers that don't care about
    intermediate progress - drains the generator and returns its final event.
    """
    async for event in chat_stream(db, user_id, session_id, message):
        if event["type"] == "done":
            return {"reply": event["reply"], "affected_resources": event["affected_resources"]}
    raise BedrockError("chat_stream ended without a final answer")


async def chat_stream(db, user_id: str, session_id: str, message: str, turn_request=None):
    """Delega en agent_loop.chat_stream (Converse API + tools + historial PG)."""
    from services.bedrock.agent_loop import chat_stream as harness_chat_stream
    from services.bedrock.agent_loop import ChatTurnRequest

    req = turn_request or ChatTurnRequest(session_id=session_id, message=message)
    async for event in harness_chat_stream(db, user_id, req):
        yield event
