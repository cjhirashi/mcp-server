"""
Pydantic schemas - Agent Bedrock chat, model switching, usage metrics,
instructions, custom tools, and memory.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# Configuración compartida
# ============================================================================

# Every schema below has a `model_id` field (an AWS Bedrock model id, not
# related to Pydantic's own `model_*` methods) - silence Pydantic v2's
# protected-namespace warning for that name across this whole module rather
# than renaming a field that matches the concept everywhere else (config.py,
# bedrock_service.py, the frontend).
_ALLOW_MODEL_ID = ConfigDict(protected_namespaces=())


# ============================================================================
# Chat — solicitudes
# ============================================================================

class BedrockChatRequest(BaseModel):
    """Harness local: historial en PG; cliente envía mensaje + contexto opcional."""

    session_id: str
    message: str
    chat_surface: str = "contextual"
    page_context: Optional[Dict[str, Any]] = None
    model_id: Optional[str] = None
    agent_profile_id: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None


# ============================================================================
# Modelos — respuestas y solicitudes
# ============================================================================

class BedrockModelOption(BaseModel):
    model_config = _ALLOW_MODEL_ID

    model_id: str
    label: str
    price_input_per_million: float
    price_output_per_million: float
    tier: Optional[str] = None


class BedrockModelStatusResponse(BaseModel):
    current_model_id: str
    available_models: List[BedrockModelOption]
    notes: Optional[str] = None


class BedrockModelSwitchRequest(BaseModel):
    model_config = _ALLOW_MODEL_ID

    model_id: str


# ============================================================================
# Métricas de uso — respuestas
# ============================================================================

class BedrockUsageByModel(BaseModel):
    model_config = _ALLOW_MODEL_ID

    model_id: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    estimated_cost_usd: float
    turns: int


class BedrockUsageByDay(BaseModel):
    day: date
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    estimated_cost_usd: float


class BedrockUsageMetricsResponse(BaseModel):
    by_model: List[BedrockUsageByModel]
    by_day: List[BedrockUsageByDay]
    total_estimated_cost_usd: float
    # Tokens servidos desde el prefijo cacheado y ahorro estimado frente a
    # pagarlos a precio de entrada normal (prompt caching de Bedrock, ADR-019).
    total_cache_read_tokens: int = 0
    total_cache_savings_usd: float = 0.0
    daily_budget_usd: Optional[float] = None
    daily_spent_usd: Optional[float] = None
    daily_remaining_usd: Optional[float] = None
    notes: Optional[str] = None


# ============================================================================
# Presupuesto — respuestas
# ============================================================================

class BedrockBudgetStatusResponse(BaseModel):
    daily_budget_usd: float
    daily_spent_usd: float
    daily_remaining_usd: float
    notes: Optional[str] = None


# ============================================================================
# Instrucciones del sistema — respuestas y solicitudes
# ============================================================================

class BedrockInstructionsResponse(BaseModel):
    system_prompt: str
    system_prompt_is_default: bool
    global_rules: str
    global_rules_is_default: bool
    notes: Optional[str] = None


class BedrockInstructionsUpdateRequest(BaseModel):
    """`system_prompt=None` (or omitted) resets to the built-in default."""

    system_prompt: Optional[str] = None


class BedrockGlobalRulesUpdateRequest(BaseModel):
    """`global_rules=None` (or omitted) resets to the built-in default."""

    global_rules: Optional[str] = None


# ============================================================================
# Perfiles de agente — respuestas y solicitudes
# ============================================================================

class BedrockAgentProfilePromptResponse(BaseModel):
    profile_id: str
    label: str
    level: int = 2
    user_facing: bool = True
    default_suffix: str
    override_suffix: Optional[str] = None
    effective_suffix: str
    is_default: bool
    notes: Optional[str] = None


class BedrockAgentProfilePromptUpdateRequest(BaseModel):
    """`system_prompt_suffix=None` clears the override for this profile."""

    system_prompt_suffix: Optional[str] = None


class BedrockAgentCatalogMethodology(BaseModel):
    id: str
    title: str
    section: Optional[str] = None
    shared: bool
    assigned: bool


class BedrockAgentCatalogSection(BaseModel):
    id: str
    label: str
    section_type: str
    path: str


class BedrockAgentDelegationTarget(BaseModel):
    id: str
    label: str
    level: int


class BedrockAgentCatalogItem(BaseModel):
    id: str
    system_name: str
    profile_id: str
    label: str
    level: int
    user_facing: bool
    can_delegate: bool
    write_enabled: bool
    domain_keys: List[str]
    resource_keys: Optional[List[str]] = None
    sections: List[BedrockAgentCatalogSection] = []
    default_model_id: Optional[str] = None
    tools: List[str]
    default_tools: List[str] = []
    override_tools: Optional[List[str]] = None
    effective_tools: List[str] = []
    has_own_memory: bool
    default_suffix: str
    override_suffix: Optional[str] = None
    effective_suffix: str
    prompt_is_default: bool
    methodology_count: int = 0
    assigned_methodologies: List[BedrockAgentCatalogMethodology] = []
    methodologies: Optional[List[BedrockAgentCatalogMethodology]] = None
    conversation_count: int = 0
    delegation_targets: List[BedrockAgentDelegationTarget] = []
    delegation_target_ids: List[str] = []
    default_delegation_target_ids: List[str] = []
    allowed_delegation_ids: List[str] = []
    delegation_is_default: bool = True
    photo_url: Optional[str] = None


class BedrockAgentPhotoUpdateRequest(BaseModel):
    photo_url: Optional[str] = Field(None, max_length=1024)


class BedrockAgentPhotoResponse(BaseModel):
    profile_id: str
    photo_url: Optional[str] = None


class BedrockAgentMethodologiesUpdateRequest(BaseModel):
    methodology_ids: List[str]


class BedrockAgentDelegationUpdateRequest(BaseModel):
    """`target_ids=None` restaura los destinos por nivel definidos en código."""

    target_ids: Optional[List[str]] = None


class BedrockAgentSectionsUpdateRequest(BaseModel):
    section_ids: List[str]


class BedrockAgentToolsUpdateRequest(BaseModel):
    """`tool_names=None` restaura el default de código (RF-002)."""

    tool_names: Optional[List[str]] = None


class BedrockAgentToolsState(BaseModel):
    profile_id: str
    default_tools: List[str]
    override_tools: Optional[List[str]] = None
    effective_tools: List[str]


class BedrockToolCatalogItem(BaseModel):
    name: str
    description: str


class BedrockAgentNote(BaseModel):
    id: str
    text: str


class BedrockAgentMemoryResponse(BaseModel):
    has_own_memory: bool
    conversation_count: int
    notes: List[BedrockAgentNote] = []


# ============================================================================
# Herramientas personalizadas — solicitudes y respuestas
# ============================================================================

class BedrockCustomToolCreateRequest(BaseModel):
    name: str
    url: str
    headers: Optional[Dict[str, str]] = None


class BedrockCustomToolResponse(BaseModel):
    id: str
    name: str
    url: str
    headers: Optional[Dict[str, str]] = None
    is_enabled: bool
    created_at: datetime
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class BedrockToolCatalogResponse(BaseModel):
    builtin: List[BedrockToolCatalogItem]
    mcp: List[BedrockCustomToolResponse]


class BedrockKnowledgeBaseReindexResult(BaseModel):
    """Resultado de `POST /bedrock/knowledge-base/reindex` (spec 003, RF-012)."""

    reindexed: Dict[str, int]
    purged_orphans: int
    users: int


# ============================================================================
# Memoria — respuestas y solicitudes
# ============================================================================

class BedrockMemoryRecordResponse(BaseModel):
    """Respuesta flexible para búsqueda semántica de hechos (Qdrant)."""

    memoryRecordId: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    score: Optional[float] = None
    createdAt: Optional[Any] = None
    namespaces: Optional[List[str]] = None
    notes: Optional[str] = None

    class Config:
        extra = "allow"


class BedrockMemoryEventResponse(BaseModel):
    """Same rationale as BedrockMemoryRecordResponse - passes through the
    real Event shape (eventId, eventTimestamp, payload, ...)."""

    eventId: Optional[str] = None
    eventTimestamp: Optional[Any] = None
    payload: Optional[List[Dict[str, Any]]] = None
    notes: Optional[str] = None

    class Config:
        extra = "allow"


class BedrockManualMemoryRequest(BaseModel):
    text: str


# ============================================================================
# Conversaciones — respuestas y solicitudes
# ============================================================================

class BedrockConversationResponse(BaseModel):
    session_id: str
    title: str
    session_type: str = "contextual"
    agent_profile_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class BedrockConversationMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class BedrockConversationRenameRequest(BaseModel):
    title: str


# ============================================================================
# Auditoría — respuestas
# ============================================================================

class BedrockAuditLogResponse(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    created_at: datetime
    notes: Optional[str] = None

    class Config:
        from_attributes = True
