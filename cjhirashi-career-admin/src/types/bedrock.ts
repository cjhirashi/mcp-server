// ============================================================================
// Agent Bedrock - TypeScript types mirroring api/src/schemas/bedrock.py
// ============================================================================

export interface BedrockModelOption {
  model_id: string
  label: string
  price_input_per_million: number
  price_output_per_million: number
}

export interface BedrockModelStatus {
  current_model_id: string
  available_models: BedrockModelOption[]
}

export interface BedrockUsageByModel {
  model_id: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  estimated_cost_usd: number
  turns: number
}

export interface BedrockUsageByDay {
  day: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  estimated_cost_usd: number
}

export interface BedrockUsageMetrics {
  by_model: BedrockUsageByModel[]
  by_day: BedrockUsageByDay[]
  total_estimated_cost_usd: number
  total_cache_read_tokens: number
  total_cache_savings_usd: number
  daily_budget_usd?: number
  daily_spent_usd?: number
  daily_remaining_usd?: number
}

/** Where the chat UI lives — general full-page vs contextual sidebar. */
export type BedrockChatSurface = 'contextual' | 'general'

/** Session bucket stored on the server (see bedrock_conversation.session_type). */
export type BedrockSessionType = 'contextual' | 'general'

/**
 * Page context sent with contextual chat turns so the harness can tailor
 * prompts and model selection (mirror of BedrockChatRequest.page_context).
 */
export interface BedrockPageContext {
  route: string
  page_title?: string
  resource_key?: string
  domain_key?: string
  /** Named chat profile key — resolved to a model id via chatSectionProfiles.ts */
  chat_profile?: string
}

/** Full payload for POST /bedrock/chat (mirror of schemas/bedrock.py). */
export interface BedrockChatAttachment {
  file_id: string
  filename: string
  mime_type?: string
  url?: string
}

export interface BedrockChatRequest {
  session_id: string
  message: string
  chat_surface?: BedrockChatSurface
  page_context?: BedrockPageContext | null
  model_id?: string | null
  agent_profile_id?: string | null
  attachments?: BedrockChatAttachment[] | null
}

// Server-persisted conversation history (see models/bedrock_conversation.py)
// - the same on every device, not client-only state.
export interface BedrockConversation {
  session_id: string
  title: string
  session_type: BedrockSessionType
  agent_profile_id?: string | null
  created_at: string
  updated_at: string
}

export interface BedrockChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface BedrockAuditLogEntry {
  id: string
  action: 'create' | 'update' | 'delete' | string
  resource_type: string
  resource_id: string | null
  old_values: Record<string, unknown> | null
  new_values: Record<string, unknown> | null
  created_at: string
}

export type TaskStatus = 'pending' | 'in_progress' | 'done' | 'cancelled' | 'failed'
export type TaskAssigneeType = 'user' | 'agent'
export type TaskPriority = 'low' | 'medium' | 'high'

export interface BedrockTask {
  id: string
  user_id: string
  title: string
  description: string | null
  status: TaskStatus | string
  notes: string | null
  assignee_type: TaskAssigneeType | string
  agent_profile_id: string | null
  scheduled_at: string | null
  due_at: string | null
  priority: TaskPriority | string
  parent_id: string | null
  sort_order: number
  is_blocking: boolean
  execute_on_turn: boolean
  turn_notified_at?: string | null
  execution_result: string | null
  executed_at: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export type BedrockTaskPayload = Partial<{
  title: string
  description: string | null
  status: string
  notes: string | null
  assignee_type: string
  agent_profile_id: string | null
  scheduled_at: string | null
  due_at: string | null
  priority: string
  parent_id: string | null
  sort_order: number
  is_blocking: boolean
  execute_on_turn: boolean
  subtasks: BedrockTaskPayload[]
}>

export interface BedrockInstructions {
  system_prompt: string
  system_prompt_is_default: boolean
  global_rules: string
  global_rules_is_default: boolean
  notes?: string
}

export interface BedrockAgentProfilePrompt {
  profile_id: string
  label: string
  level?: number
  user_facing?: boolean
  default_suffix: string
  override_suffix: string | null
  effective_suffix: string
  is_default: boolean
}

export interface BedrockAgentCatalogMethodology {
  id: string
  title: string
  section: string | null
  shared: boolean
  assigned: boolean
}

export interface BedrockAgentCatalogSection {
  id: string
  label: string
  section_type: string
  path: string
}

export interface BedrockAgentDelegationTarget {
  id: string
  label: string
  level: number
}

export interface BedrockAgentCatalogItem {
  id: string
  system_name: string
  profile_id: string
  label: string
  level: number
  user_facing: boolean
  can_delegate: boolean
  write_enabled: boolean
  domain_keys: string[]
  resource_keys: string[] | null
  sections: BedrockAgentCatalogSection[]
  default_model_id: string | null
  tools: string[]
  default_tools: string[]
  override_tools: string[] | null
  effective_tools: string[]
  has_own_memory: boolean
  default_suffix: string
  override_suffix: string | null
  effective_suffix: string
  prompt_is_default: boolean
  methodology_count: number
  assigned_methodologies: BedrockAgentCatalogMethodology[]
  methodologies?: BedrockAgentCatalogMethodology[]
  conversation_count: number
  delegation_targets: BedrockAgentDelegationTarget[]
  delegation_target_ids: string[]
  default_delegation_target_ids: string[]
  allowed_delegation_ids: string[]
  delegation_is_default: boolean
  photo_url?: string | null
}

export interface BedrockAgentNote {
  id: string
  text: string
}

export interface BedrockAgentMemory {
  has_own_memory: boolean
  conversation_count: number
  notes: BedrockAgentNote[]
}

export interface BedrockCustomTool {
  id: string
  name: string
  url: string
  headers: Record<string, string> | null
  is_enabled: boolean
  created_at: string
}

export interface BedrockAgentToolsState {
  profile_id: string
  default_tools: string[]
  override_tools: string[] | null
  effective_tools: string[]
}

export interface BedrockToolCatalogItem {
  name: string
  description: string
}

export interface BedrockToolCatalog {
  builtin: BedrockToolCatalogItem[]
  mcp: BedrockCustomTool[]
}

// Flexible shape for semantic memory hits from Qdrant (memoryRecordId, content, score, …).
export interface BedrockMemoryEvent {
  eventId?: string
  eventTimestamp?: string | number
  payload?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export interface BedrockMemoryRecord {
  memoryRecordId?: string
  content?: Record<string, unknown>
  score?: number
  createdAt?: string | number
  namespaces?: string[]
  [key: string]: unknown
}
