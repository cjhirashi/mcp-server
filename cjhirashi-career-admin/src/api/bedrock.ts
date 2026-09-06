import { axiosInstance, API_BASE_URL } from './client'
import { useAuthStore } from '@/stores/authStore'
import {
  BedrockAuditLogEntry,
  BedrockChatMessage,
  BedrockChatRequest,
  BedrockConversation,
  BedrockCustomTool,
  BedrockInstructions,
  BedrockAgentProfilePrompt,
  BedrockAgentCatalogItem,
  BedrockAgentCatalogMethodology,
  BedrockAgentMemory,
  BedrockAgentNote,
  BedrockAgentToolsState,
  BedrockToolCatalog,
  BedrockMemoryEvent,
  BedrockMemoryRecord,
  BedrockModelStatus,
  BedrockSessionType,
  BedrockUsageMetrics,
} from '@/types/bedrock'

/**
 * Client for Agent Bedrock (Harness local Converse API).
 *
 * `chat` sends the newest message plus session/context metadata — historial
 * en PostgreSQL (`services/bedrock/history_manager.py`).
 *
 * `chat` uses `fetch` directly, not `axiosInstance` - it needs to read the
 * response as a live Server-Sent Events stream (status updates as the agent
 * works, then a final `done`/`error` event), and axios's response types
 * don't expose the raw ReadableStream the way `fetch` does. This means it
 * doesn't get axios's interceptor-based 401 refresh-token handling (see
 * client.ts) - an expired token surfaces as a plain auth error here instead
 * of transparently refreshing. Every other call below keeps using axios.
 */
const CONTROL_PLANE_TIMEOUT_MS = 30_000

// A tool-use turn can take a while for real (AWS round trips add up, see
// chat_stream's docstring in bedrock_service.py) - 4 minutes is a generous
// ceiling for the worst realistic case, not an arbitrary guess.
const CHAT_TIMEOUT_MS = 240_000

export interface BedrockChatResult {
  reply: string
  affected_resources: string[]
}

export interface BedrockDelegationStartEvent {
  agent_profile_id: string
  label: string
  task_preview: string
}

export interface BedrockDelegationEndEvent {
  agent_profile_id: string
  success: boolean
  summary_preview: string
}

/** Callbacks for SSE events emitted during a chat turn. */
export interface BedrockChatStreamCallbacks {
  onStatus?: (message: string) => void
  onDelegationStart?: (event: BedrockDelegationStartEvent) => void
  onDelegationEnd?: (event: BedrockDelegationEndEvent) => void
}

function normalizeCallbacks(
  callbacks?: BedrockChatStreamCallbacks | ((message: string) => void)
): BedrockChatStreamCallbacks {
  if (typeof callbacks === 'function') return { onStatus: callbacks }
  return callbacks ?? {}
}

export const bedrockApi = {
  /**
   * Streams the turn's progress via callbacks as the agent works, then
   * resolves with the final reply. Accepts the full BedrockChatRequest
   * payload (chat_surface, page_context, model_id, agent_profile_id, …).
   */
  chat: async (
    payload: BedrockChatRequest,
    callbacks?: BedrockChatStreamCallbacks | ((message: string) => void)
  ): Promise<BedrockChatResult> => {
    const { onStatus, onDelegationStart, onDelegationEnd } = normalizeCallbacks(callbacks)
    const accessToken = useAuthStore.getState().accessToken
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS)

    let response: Response
    try {
      response = await fetch(`${API_BASE_URL}/bedrock/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({
          session_id: payload.session_id,
          message: payload.message,
          chat_surface: payload.chat_surface ?? 'contextual',
          page_context: payload.page_context ?? null,
          model_id: payload.model_id ?? null,
          agent_profile_id: payload.agent_profile_id ?? null,
          attachments: payload.attachments ?? null,
        }),
        signal: controller.signal,
      })
    } catch (err) {
      clearTimeout(timeoutId)
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new Error(`timeout of ${CHAT_TIMEOUT_MS}ms exceeded`)
      }
      throw err
    }

    if (!response.ok || !response.body) {
      clearTimeout(timeoutId)
      let detail = `HTTP ${response.status}`
      try {
        const data = await response.json()
        detail = data.detail || detail
      } catch {
        // body wasn't JSON - keep the plain HTTP status message
      }
      throw new Error(detail)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let result: BedrockChatResult | null = null
    let streamError: string | null = null

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const events = buffer.split('\n\n')
        buffer = events.pop() ?? ''
        for (const raw of events) {
          const line = raw.trim()
          if (!line.startsWith('data: ')) continue
          const event = JSON.parse(line.slice('data: '.length))
          if (event.type === 'status') {
            onStatus?.(event.message)
          } else if (event.type === 'delegation_start') {
            onDelegationStart?.({
              agent_profile_id: event.agent_profile_id,
              label: event.label,
              task_preview: event.task_preview,
            })
            onStatus?.(`Delegando a ${event.label}…`)
          } else if (event.type === 'delegation_end') {
            onDelegationEnd?.({
              agent_profile_id: event.agent_profile_id,
              success: event.success,
              summary_preview: event.summary_preview,
            })
            onStatus?.('Especialista terminó')
          } else if (event.type === 'done') {
            result = { reply: event.reply, affected_resources: event.affected_resources }
          } else if (event.type === 'error') {
            streamError = event.message
          }
        }
      }
    } finally {
      clearTimeout(timeoutId)
    }

    if (streamError) throw new Error(streamError)
    if (!result) throw new Error('El stream terminó sin una respuesta final')
    return result
  },

  getModel: async (): Promise<BedrockModelStatus> => {
    const response = await axiosInstance.get<BedrockModelStatus>('/bedrock/model', {
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  switchModel: async (modelId: string): Promise<BedrockModelStatus> => {
    const response = await axiosInstance.post<BedrockModelStatus>(
      '/bedrock/model',
      { model_id: modelId },
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  usageMetrics: async (days = 30): Promise<BedrockUsageMetrics> => {
    const response = await axiosInstance.get<BedrockUsageMetrics>('/bedrock/usage-metrics', {
      params: { days },
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  getInstructions: async (): Promise<BedrockInstructions> => {
    const response = await axiosInstance.get<BedrockInstructions>('/bedrock/instructions', {
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  /** `systemPrompt: null` resets to the built-in default. */
  updateInstructions: async (systemPrompt: string | null): Promise<BedrockInstructions> => {
    const response = await axiosInstance.put<BedrockInstructions>(
      '/bedrock/instructions',
      { system_prompt: systemPrompt },
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  /** `globalRules: null` resets to the built-in default. */
  updateGlobalRules: async (globalRules: string | null): Promise<BedrockInstructions> => {
    const response = await axiosInstance.put<BedrockInstructions>(
      '/bedrock/global-rules',
      { global_rules: globalRules },
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  listAgentProfilePrompts: async (): Promise<BedrockAgentProfilePrompt[]> => {
    const response = await axiosInstance.get<BedrockAgentProfilePrompt[]>('/bedrock/agent-profiles', {
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  /** `systemPromptSuffix: null` resets to the built-in default for that profile. */
  updateAgentProfilePrompt: async (
    profileId: string,
    systemPromptSuffix: string | null
  ): Promise<BedrockAgentProfilePrompt> => {
    const response = await axiosInstance.put<BedrockAgentProfilePrompt>(
      `/bedrock/agent-profiles/${profileId}/prompt`,
      { system_prompt_suffix: systemPromptSuffix },
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  listAgentCatalog: async (): Promise<BedrockAgentCatalogItem[]> => {
    const response = await axiosInstance.get<BedrockAgentCatalogItem[]>(
      '/bedrock/agent-profiles/catalog',
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  getAgentCatalogItem: async (profileId: string): Promise<BedrockAgentCatalogItem> => {
    const response = await axiosInstance.get<BedrockAgentCatalogItem>(
      `/bedrock/agent-profiles/${profileId}/catalog`,
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  updateAgentMethodologies: async (
    profileId: string,
    methodologyIds: string[]
  ): Promise<BedrockAgentCatalogMethodology[]> => {
    const response = await axiosInstance.put<BedrockAgentCatalogMethodology[]>(
      `/bedrock/agent-profiles/${profileId}/methodologies`,
      { methodology_ids: methodologyIds },
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  getAgentTools: async (profileId: string): Promise<BedrockAgentToolsState> => {
    const response = await axiosInstance.get<BedrockAgentToolsState>(
      `/bedrock/agent-profiles/${profileId}/tools`,
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  /** `toolNames: null` restores the code default for that profile. */
  updateAgentTools: async (
    profileId: string,
    toolNames: string[] | null
  ): Promise<BedrockAgentToolsState> => {
    const response = await axiosInstance.put<BedrockAgentToolsState>(
      `/bedrock/agent-profiles/${profileId}/tools`,
      { tool_names: toolNames },
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  listToolsCatalog: async (): Promise<BedrockToolCatalog> => {
    const response = await axiosInstance.get<BedrockToolCatalog>('/bedrock/tools/catalog', {
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  updateAgentDelegation: async (
    profileId: string,
    targetIds: string[] | null
  ): Promise<{
    profile_id: string
    default_ids: string[]
    effective_ids: string[]
    is_default: boolean
  }> => {
    const response = await axiosInstance.put(
      `/bedrock/agent-profiles/${profileId}/delegation`,
      { target_ids: targetIds },
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  updateAgentSections: async (profileId: string, sectionIds: string[]): Promise<unknown> => {
    const response = await axiosInstance.put(
      `/bedrock/agent-profiles/${profileId}/sections`,
      { section_ids: sectionIds },
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  updateAgentPhoto: async (profileId: string, photoUrl: string | null): Promise<{ profile_id: string; photo_url: string | null }> => {
    const response = await axiosInstance.put<{ profile_id: string; photo_url: string | null }>(
      `/bedrock/agent-profiles/${profileId}/photo`,
      { photo_url: photoUrl },
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  getAgentMemory: async (profileId: string): Promise<BedrockAgentMemory> => {
    const response = await axiosInstance.get<BedrockAgentMemory>(
      `/bedrock/agent-profiles/${profileId}/memory`,
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  addAgentMemoryNote: async (profileId: string, text: string): Promise<BedrockAgentNote> => {
    const response = await axiosInstance.post<BedrockAgentNote>(
      `/bedrock/agent-profiles/${profileId}/memory/notes`,
      { text },
      { timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  deleteAgentMemoryNote: async (profileId: string, noteId: string): Promise<void> => {
    await axiosInstance.delete(`/bedrock/agent-profiles/${profileId}/memory/notes/${noteId}`, {
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
  },

  listTools: async (): Promise<BedrockCustomTool[]> => {
    const response = await axiosInstance.get<BedrockCustomTool[]>('/bedrock/tools', {
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  createTool: async (payload: { name: string; url: string; headers?: Record<string, string> }): Promise<BedrockCustomTool> => {
    const response = await axiosInstance.post<BedrockCustomTool>('/bedrock/tools', payload, {
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  setToolEnabled: async (id: string, isEnabled: boolean): Promise<BedrockCustomTool> => {
    const response = await axiosInstance.put<BedrockCustomTool>(
      `/bedrock/tools/${id}/enabled`,
      null,
      { params: { is_enabled: isEnabled }, timeout: CONTROL_PLANE_TIMEOUT_MS }
    )
    return response.data
  },

  deleteTool: async (id: string): Promise<void> => {
    await axiosInstance.delete(`/bedrock/tools/${id}`, { timeout: CONTROL_PLANE_TIMEOUT_MS })
  },

  getMemoryEvents: async (sessionId: string): Promise<BedrockMemoryEvent[]> => {
    const response = await axiosInstance.get<BedrockMemoryEvent[]>('/bedrock/memory/events', {
      params: { session_id: sessionId },
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  getMemoryRecords: async (query: string): Promise<BedrockMemoryRecord[]> => {
    const response = await axiosInstance.get<BedrockMemoryRecord[]>('/bedrock/memory/records', {
      params: { query },
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  addManualMemory: async (text: string): Promise<void> => {
    await axiosInstance.post('/bedrock/memory/manual', { text }, { timeout: CONTROL_PLANE_TIMEOUT_MS })
  },

  // Conversations - server-persisted, same on every device (see
  // models/bedrock_conversation.py). Messages are written by the backend
  // itself as part of /bedrock/chat, not by these calls.
  listConversations: async (
    sessionType?: BedrockSessionType,
    agentProfileId?: string
  ): Promise<BedrockConversation[]> => {
    const response = await axiosInstance.get<BedrockConversation[]>('/bedrock/conversations', {
      params: {
        ...(sessionType ? { session_type: sessionType } : {}),
        ...(agentProfileId ? { agent_profile_id: agentProfileId } : {}),
      },
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  getConversationMessages: async (sessionId: string): Promise<BedrockChatMessage[]> => {
    const response = await axiosInstance.get<BedrockChatMessage[]>(`/bedrock/conversations/${sessionId}/messages`, {
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  renameConversation: async (sessionId: string, title: string): Promise<void> => {
    await axiosInstance.put(`/bedrock/conversations/${sessionId}`, { title }, { timeout: CONTROL_PLANE_TIMEOUT_MS })
  },

  deleteConversation: async (sessionId: string): Promise<void> => {
    await axiosInstance.delete(`/bedrock/conversations/${sessionId}`, { timeout: CONTROL_PLANE_TIMEOUT_MS })
  },

  // Audit log (bitácora) - every create/update/delete the agent has made.
  getAuditLog: async (limit = 50, offset = 0): Promise<BedrockAuditLogEntry[]> => {
    const response = await axiosInstance.get<BedrockAuditLogEntry[]>('/bedrock/audit-log', {
      params: { limit, offset },
      timeout: CONTROL_PLANE_TIMEOUT_MS,
    })
    return response.data
  },

  restoreAuditEntry: async (auditId: string): Promise<void> => {
    await axiosInstance.post(`/bedrock/audit-log/${auditId}/restore`, null, { timeout: CONTROL_PLANE_TIMEOUT_MS })
  },
}
