"""
Agent Bedrock - chat, model switching, and usage-cost metrics.

No auth of its own: `get_current_user` is the exact same dependency every
other authenticated route in this API uses. Bedrock never gets a distinct
authorization scope - it operates with whatever the calling Admin Panel
session already has (see docs/01-INTRODUCTION.md, Security Model).
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from middleware.auth import get_current_user
from models.bedrock_usage_log import BedrockUsageLog
from models.user import User
from schemas.bedrock import (
    BedrockAgentProfilePromptResponse,
    BedrockAgentProfilePromptUpdateRequest,
    BedrockAgentCatalogItem,
    BedrockAgentCatalogMethodology,
    BedrockAgentDelegationUpdateRequest,
    BedrockAgentMemoryResponse,
    BedrockAgentMethodologiesUpdateRequest,
    BedrockAgentNote,
    BedrockAgentPhotoResponse,
    BedrockAgentPhotoUpdateRequest,
    BedrockAgentSectionsUpdateRequest,
    BedrockAgentToolsState,
    BedrockAgentToolsUpdateRequest,
    BedrockAuditLogResponse,
    BedrockChatRequest,
    BedrockConversationMessageResponse,
    BedrockConversationRenameRequest,
    BedrockConversationResponse,
    BedrockCustomToolCreateRequest,
    BedrockCustomToolResponse,
    BedrockGlobalRulesUpdateRequest,
    BedrockInstructionsResponse,
    BedrockInstructionsUpdateRequest,
    BedrockManualMemoryRequest,
    BedrockMemoryEventResponse,
    BedrockMemoryRecordResponse,
    BedrockModelOption,
    BedrockModelStatusResponse,
    BedrockModelSwitchRequest,
    BedrockToolCatalogResponse,
    BedrockBudgetStatusResponse,
    BedrockUsageByDay,
    BedrockUsageByModel,
    BedrockUsageMetricsResponse,
)
from services import bedrock_service
from services.bedrock import profile_prompts
from services.bedrock.agent_profiles import get_profile
from services.bedrock_service import BedrockError
from services.error_reporting import report_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bedrock", tags=["Bedrock"])


def _require_configured() -> None:
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent Bedrock is not configured (missing AWS credentials)",
        )


async def _sse_chat_events(db: AsyncSession, user_id: str, payload: BedrockChatRequest):
    """SSE desde chat_stream (Converse API + tools)."""
    from services.bedrock.agent_loop import ChatTurnRequest

    turn = ChatTurnRequest(
        session_id=payload.session_id,
        message=payload.message,
        chat_surface=payload.chat_surface,
        page_context=payload.page_context,
        model_id=payload.model_id,
        agent_profile_id=payload.agent_profile_id,
        attachments=payload.attachments,
    )

    queue: asyncio.Queue = asyncio.Queue()

    async def _producer() -> None:
        try:
            async for event in bedrock_service.chat_stream(
                db, user_id, payload.session_id, payload.message, turn_request=turn
            ):
                await queue.put(("event", event))
        except BedrockError as e:
            logger.error("Bedrock chat failed: %s", e)
            report_error(
                str(e), "route:bedrock.chat_stream", error_type="BedrockError", exc=e,
                context={"session_id": payload.session_id, "agent_profile_id": payload.agent_profile_id},
                severity="error",
            )
            await queue.put(("error", str(e)))
        except Exception as e:
            logger.exception("Unexpected error in Bedrock chat stream")
            report_error(
                str(e) or "Unexpected error in Bedrock chat stream",
                "route:bedrock.chat_stream", error_type=type(e).__name__, exc=e,
                context={"session_id": payload.session_id, "agent_profile_id": payload.agent_profile_id},
                severity="critical",
            )
            await queue.put(("error", f"Error interno del agente: {e}"))
        finally:
            await queue.put(("done", None))

    producer_task = asyncio.create_task(_producer())
    try:
        while True:
            try:
                kind, payload_item = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if kind == "done":
                break
            if kind == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': payload_item})}\n\n"
                break
            yield f"data: {json.dumps(payload_item)}\n\n"
    finally:
        if not producer_task.done():
            producer_task.cancel()
            try:
                await producer_task
            except asyncio.CancelledError:
                pass


@router.post("/chat", summary="Chat with Agent Bedrock (Server-Sent Events: status/done/error)")
async def chat(
    payload: BedrockChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_configured()

    return StreamingResponse(
        _sse_chat_events(db, current_user.id, payload),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/model", response_model=BedrockModelStatusResponse, summary="Get the active chat model and the switchable allow-list")
async def get_model(current_user: User = Depends(get_current_user)):
    _require_configured()
    try:
        current_model_id = await bedrock_service.get_current_model()
    except BedrockError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    available = [
        BedrockModelOption(model_id=model_id, **info)
        for model_id, info in settings.BEDROCK_AVAILABLE_MODELS.items()
    ]
    return BedrockModelStatusResponse(current_model_id=current_model_id, available_models=available)


@router.post("/model", response_model=BedrockModelStatusResponse, summary="Switch the chat model")
async def switch_model(
    payload: BedrockModelSwitchRequest,
    current_user: User = Depends(get_current_user),
):
    _require_configured()
    if payload.model_id not in settings.BEDROCK_AVAILABLE_MODELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown model_id: {payload.model_id}",
        )

    try:
        await bedrock_service.switch_model(payload.model_id)
    except BedrockError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    available = [
        BedrockModelOption(model_id=model_id, **info)
        for model_id, info in settings.BEDROCK_AVAILABLE_MODELS.items()
    ]
    return BedrockModelStatusResponse(current_model_id=payload.model_id, available_models=available)


@router.get("/usage-metrics", response_model=BedrockUsageMetricsResponse, summary="Token usage and estimated cost of the chat assistant")
async def get_usage_metrics(
    days: int = Query(30, ge=1, le=365, description="How many most-recent days to include"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user.id
    from services.bedrock import usage_logger

    by_model_stmt = (
        select(
            BedrockUsageLog.model_id,
            func.sum(BedrockUsageLog.input_tokens),
            func.sum(BedrockUsageLog.output_tokens),
            func.sum(BedrockUsageLog.cache_read_tokens),
            func.sum(BedrockUsageLog.cache_write_tokens),
            func.sum(BedrockUsageLog.estimated_cost_usd),
            func.count(),
        )
        .where(BedrockUsageLog.user_id == user_id)
        .group_by(BedrockUsageLog.model_id)
        .order_by(func.sum(BedrockUsageLog.estimated_cost_usd).desc())
    )
    by_model_rows = (await db.execute(by_model_stmt)).all()
    by_model = [
        BedrockUsageByModel(
            model_id=model_id,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            cache_read_tokens=int(cache_read or 0),
            cache_write_tokens=int(cache_write or 0),
            estimated_cost_usd=float(cost or 0),
            turns=turns,
        )
        for model_id, input_tokens, output_tokens, cache_read, cache_write, cost, turns in by_model_rows
    ]

    day_col = func.date(BedrockUsageLog.created_at)
    by_day_stmt = (
        select(
            day_col,
            func.sum(BedrockUsageLog.input_tokens),
            func.sum(BedrockUsageLog.output_tokens),
            func.sum(BedrockUsageLog.cache_read_tokens),
            func.sum(BedrockUsageLog.cache_write_tokens),
            func.sum(BedrockUsageLog.estimated_cost_usd),
        )
        .where(
            BedrockUsageLog.user_id == user_id,
            BedrockUsageLog.created_at >= func.now() - func.make_interval(0, 0, 0, days),
        )
        .group_by(day_col)
        .order_by(day_col.asc())
    )
    by_day_rows = (await db.execute(by_day_stmt)).all()
    by_day = [
        BedrockUsageByDay(
            day=day,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            cache_read_tokens=int(cache_read or 0),
            cache_write_tokens=int(cache_write or 0),
            estimated_cost_usd=float(cost or 0),
        )
        for day, input_tokens, output_tokens, cache_read, cache_write, cost in by_day_rows
    ]

    total_cost = sum(m.estimated_cost_usd for m in by_model)
    total_cache_read_tokens = sum(m.cache_read_tokens for m in by_model)
    total_cache_savings_usd = sum(
        usage_logger.cache_read_savings_usd(m.model_id, m.cache_read_tokens) for m in by_model
    )

    daily_budget = float(settings.BEDROCK_DAILY_BUDGET_USD)
    from services.bedrock.budget import get_daily_spend_usd, get_remaining_budget_usd

    daily_spent = await get_daily_spend_usd(db, user_id)
    daily_remaining = await get_remaining_budget_usd(db, user_id, daily_budget)

    return BedrockUsageMetricsResponse(
        by_model=by_model,
        by_day=by_day,
        total_estimated_cost_usd=total_cost,
        total_cache_read_tokens=total_cache_read_tokens,
        total_cache_savings_usd=total_cache_savings_usd,
        daily_budget_usd=daily_budget,
        daily_spent_usd=daily_spent,
        daily_remaining_usd=daily_remaining,
    )


@router.get("/budget", response_model=BedrockBudgetStatusResponse, summary="Daily inference budget status")
async def get_budget_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.bedrock.budget import get_daily_spend_usd, get_remaining_budget_usd

    daily_budget = float(settings.BEDROCK_DAILY_BUDGET_USD)
    spent = await get_daily_spend_usd(db, current_user.id)
    remaining = await get_remaining_budget_usd(db, current_user.id, daily_budget)
    return BedrockBudgetStatusResponse(
        daily_budget_usd=daily_budget,
        daily_spent_usd=spent,
        daily_remaining_usd=remaining,
    )


# ---------------------------------------------------------------------------
# Instructions (system prompt + global rules)
# ---------------------------------------------------------------------------

async def _instructions_response(db: AsyncSession) -> BedrockInstructionsResponse:
    """Combined state of the system prompt and the global rules - both
    /instructions and /global-rules return this same shape so the frontend
    can refresh the whole editor from a single response."""
    prompt = await bedrock_service.get_system_prompt(db)
    rules = await bedrock_service.get_global_rules(db)
    return BedrockInstructionsResponse(
        system_prompt=prompt,
        system_prompt_is_default=prompt == bedrock_service.default_system_prompt(),
        global_rules=rules,
        global_rules_is_default=rules == bedrock_service.default_global_rules(),
    )


@router.get("/instructions", response_model=BedrockInstructionsResponse, summary="Get the agent's current system prompt and global rules")
async def get_instructions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _instructions_response(db)


@router.put("/instructions", response_model=BedrockInstructionsResponse, summary="Set (or clear) the agent's system prompt override")
async def update_instructions(
    payload: BedrockInstructionsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    text = payload.system_prompt.strip() if payload.system_prompt else None
    await bedrock_service.set_system_prompt(db, text)
    return await _instructions_response(db)


@router.put("/global-rules", response_model=BedrockInstructionsResponse, summary="Set (or clear) the agent's global rules override")
async def update_global_rules(
    payload: BedrockGlobalRulesUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    text = payload.global_rules.strip() if payload.global_rules else None
    await bedrock_service.set_global_rules(db, text)
    return await _instructions_response(db)


@router.get(
    "/agent-profiles",
    response_model=list[BedrockAgentProfilePromptResponse],
    summary="List agent profiles with prompt suffix defaults and overrides",
)
async def list_agent_profile_prompts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await profile_prompts.list_profile_prompts(db)


@router.get(
    "/agent-profiles/catalog",
    response_model=list[BedrockAgentCatalogItem],
    summary="Catálogo de agentes: definición de código + estado editable",
)
async def list_agent_catalog(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.bedrock import profile_catalog

    return await profile_catalog.list_catalog(db, current_user.id)


@router.put(
    "/agent-profiles/{profile_id}/prompt",
    response_model=BedrockAgentProfilePromptResponse,
    summary="Set or clear the system prompt suffix override for one agent profile",
)
async def update_agent_profile_prompt(
    profile_id: str,
    payload: BedrockAgentProfilePromptUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        get_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")
    try:
        return await profile_prompts.set_profile_prompt_suffix(
            db,
            profile_id,
            payload.system_prompt_suffix,
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")


@router.get(
    "/agent-profiles/{profile_id}/catalog",
    response_model=BedrockAgentCatalogItem,
    summary="Detalle de un agente del catálogo",
)
async def get_agent_catalog_item(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.bedrock import profile_catalog

    try:
        get_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")
    return await profile_catalog.get_catalog_item(db, current_user.id, profile_id)


@router.put(
    "/agent-profiles/{profile_id}/photo",
    response_model=BedrockAgentPhotoResponse,
    summary="Foto del agente (URL pública del bucket)",
)
async def update_agent_photo(
    profile_id: str,
    payload: BedrockAgentPhotoUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.bedrock import profile_photos

    try:
        get_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")
    return await profile_photos.set_photo(db, profile_id, payload.photo_url)


@router.put(
    "/agent-profiles/{profile_id}/delegation",
    summary="Destinos de delegación editables (subset de los permitidos por nivel)",
)
async def update_agent_delegation(
    profile_id: str,
    payload: BedrockAgentDelegationUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.bedrock import profile_delegation

    try:
        get_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")
    return await profile_delegation.set_delegation_targets(db, profile_id, payload.target_ids)


@router.put(
    "/agent-profiles/{profile_id}/sections",
    summary="Secciones del Admin que este agente gestiona",
)
async def update_agent_sections(
    profile_id: str,
    payload: BedrockAgentSectionsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services import section_catalog

    try:
        get_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")
    try:
        return await section_catalog.set_agent_sections(db, profile_id, payload.section_ids)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put(
    "/agent-profiles/{profile_id}/methodologies",
    response_model=list[BedrockAgentCatalogMethodology],
    summary="Asigna las metodologías que este agente debe consultar",
)
async def update_agent_methodologies(
    profile_id: str,
    payload: BedrockAgentMethodologiesUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.methodology_scope import set_agent_methodologies

    try:
        get_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")
    return await set_agent_methodologies(
        db, current_user.id, profile_id, payload.methodology_ids
    )


@router.get(
    "/agent-profiles/{profile_id}/tools",
    response_model=BedrockAgentToolsState,
    summary="Estado de herramientas de un agente (default/override/efectivo)",
)
async def get_agent_tools(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.bedrock import profile_tools

    try:
        profile = get_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")
    return await profile_tools.get_tool_state(db, profile)


@router.put(
    "/agent-profiles/{profile_id}/tools",
    response_model=BedrockAgentToolsState,
    summary="Configura las herramientas que este agente puede usar",
)
async def update_agent_tools(
    profile_id: str,
    payload: BedrockAgentToolsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.bedrock import profile_tools

    try:
        get_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")
    try:
        return await profile_tools.set_tool_override(db, profile_id, payload.tool_names)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/agent-profiles/{profile_id}/memory",
    response_model=BedrockAgentMemoryResponse,
    summary="Memoria propia del agente (L1/L2: notas + conversaciones)",
)
async def get_agent_memory(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.bedrock import history_manager, local_memory

    try:
        profile = get_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")
    conversations = await history_manager.list_conversations(
        db, current_user.id, agent_profile_id=profile.id
    )
    notes = []
    if profile.user_facing:
        notes = await local_memory.list_agent_notes(current_user.id, profile.id)
    return BedrockAgentMemoryResponse(
        has_own_memory=profile.user_facing,
        conversation_count=len(conversations),
        notes=notes,
    )


@router.post(
    "/agent-profiles/{profile_id}/memory/notes",
    response_model=BedrockAgentNote,
    summary="Añade una nota de memoria propia (solo L1/L2)",
)
async def create_agent_memory_note(
    profile_id: str,
    payload: BedrockManualMemoryRequest,
    current_user: User = Depends(get_current_user),
):
    from services.bedrock import local_memory

    try:
        profile = get_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")
    if not profile.user_facing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los agentes L3 no tienen memoria propia",
        )
    return await local_memory.create_agent_note(current_user.id, profile.id, payload.text)


@router.delete(
    "/agent-profiles/{profile_id}/memory/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Elimina una nota de memoria propia",
)
async def delete_agent_memory_note(
    profile_id: str,
    note_id: str,
    current_user: User = Depends(get_current_user),
):
    from services.bedrock import local_memory

    try:
        profile = get_profile(profile_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent profile")
    if not profile.user_facing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los agentes L3 no tienen memoria propia",
        )
    await local_memory.delete_agent_note(note_id)


# ---------------------------------------------------------------------------
# Custom tools (MCP integrations)
# ---------------------------------------------------------------------------

@router.get("/tools", response_model=list[BedrockCustomToolResponse], summary="List registered MCP tool servers")
async def list_tools(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await bedrock_service.list_custom_tools(db)


@router.get(
    "/tools/catalog",
    response_model=BedrockToolCatalogResponse,
    summary="Catálogo read-only de herramientas (integradas + MCP)",
)
async def get_tools_catalog(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.bedrock import profile_tools

    builtin = profile_tools.list_builtin_tool_catalog()
    mcp = await bedrock_service.list_custom_tools(db)
    return {"builtin": builtin, "mcp": mcp}


@router.post("/tools", response_model=BedrockCustomToolResponse, status_code=status.HTTP_201_CREATED, summary="Register a new MCP tool server")
async def create_tool(
    payload: BedrockCustomToolCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await bedrock_service.create_custom_tool(db, payload.name, payload.url, payload.headers)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/tools/{tool_id}/enabled", response_model=BedrockCustomToolResponse, summary="Enable or disable a registered MCP tool server")
async def set_tool_enabled(
    tool_id: str,
    is_enabled: bool,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tool = await bedrock_service.set_custom_tool_enabled(db, tool_id, is_enabled)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    return tool


@router.delete("/tools/{tool_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a registered MCP tool server")
async def delete_tool(
    tool_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await bedrock_service.delete_custom_tool(db, tool_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")


# ---------------------------------------------------------------------------
# Memory (read-only)
# ---------------------------------------------------------------------------

@router.get("/knowledge/search", summary="Búsqueda semántica Qdrant (Harness local)")
async def search_knowledge(
    q: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
):
    from services.bedrock.embeddings import embed_text
    from services import qdrant_service

    vector = await embed_text(q)
    results = await qdrant_service.search(user_id=current_user.id, vector=vector, top_k=top_k)
    return {"results": results}


@router.get("/memory/events", response_model=list[BedrockMemoryEventResponse], summary="Raw short-term memory events for one conversation")
async def get_memory_events(
    session_id: str = Query(..., description="A conversation's session_id"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_configured()
    from services.bedrock import local_memory

    try:
        return await local_memory.list_memory_events(db, current_user.id, session_id)
    except BedrockError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.get("/memory/records", response_model=list[BedrockMemoryRecordResponse], summary="Semantic search over durable facts the agent has learned about you")
async def get_memory_records(
    query: str = Query(..., min_length=1, description="What to search for, e.g. 'preferencias de vacantes'"),
    top_k: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    _require_configured()
    from services.bedrock import local_memory

    try:
        return await local_memory.retrieve_memory_records(current_user.id, query, top_k)
    except BedrockError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


@router.post("/memory/manual", status_code=status.HTTP_201_CREATED, summary="Manually seed a fact into the agent's long-term memory")
async def add_manual_memory(
    payload: BedrockManualMemoryRequest,
    current_user: User = Depends(get_current_user),
):
    _require_configured()
    from services.bedrock import local_memory

    try:
        await local_memory.create_manual_memory(current_user.id, payload.text)
    except BedrockError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Conversations (server-side history, same on every device)
# ---------------------------------------------------------------------------

@router.get("/conversations", response_model=list[BedrockConversationResponse], summary="List this user's conversations")
async def list_conversations(
    session_type: str | None = Query(None, description="Filter: contextual | general"),
    agent_profile_id: str | None = Query(
        None, description="Filter by specialist profile id (identity, search, orchestrator, …)"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.bedrock.history_manager import list_conversations as list_conv

    return await list_conv(db, current_user.id, session_type, agent_profile_id)


@router.get("/conversations/{session_id}/messages", response_model=list[BedrockConversationMessageResponse], summary="Get one conversation's messages")
async def get_conversation_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from services.bedrock.reply_text import sanitize_assistant_reply

    messages = await bedrock_service.get_conversation_messages(db, current_user.id, session_id)
    return [
        BedrockConversationMessageResponse(
            id=m.id,
            role=m.role,
            content=sanitize_assistant_reply(m.content) if m.role == "assistant" else m.content,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.put("/conversations/{session_id}", summary="Rename a conversation")
async def rename_conversation(
    session_id: str,
    payload: BedrockConversationRenameRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    renamed = await bedrock_service.rename_conversation(db, current_user.id, session_id, payload.title)
    if not renamed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return {"status": "ok"}


@router.delete("/conversations/{session_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a conversation")
async def delete_conversation(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await bedrock_service.delete_conversation(db, current_user.id, session_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


# ---------------------------------------------------------------------------
# Audit log (bitácora) - every create/update/delete the agent has made,
# with the full before/after record state. See services/bedrock_service.py's
# _record_audit - this is read-only plus a one-click restore for deletes.
# ---------------------------------------------------------------------------

@router.get("/audit-log", response_model=list[BedrockAuditLogResponse], summary="The agent's change history")
async def get_audit_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await bedrock_service.list_audit_log(db, current_user.id, limit, offset)


@router.post("/audit-log/{audit_id}/restore", summary="Restore a record the agent deleted")
async def restore_audit_entry(
    audit_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await bedrock_service.restore_audit_entry(db, current_user.id, audit_id)
    except BedrockError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
