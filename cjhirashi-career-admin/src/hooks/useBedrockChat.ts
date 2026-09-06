import { useLayoutEffect, useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { bedrockApi } from '@/api/bedrock'
import { agentTasksApi } from '@/api/agentTasks'
import { invalidateAdminDataViews } from '@/hooks/invalidateAdminDataViews'
import { conversationBucket, useBedrockChatStore } from '@/stores/bedrockChatStore'
import { AGENT_ORCHESTRATOR, resolveAgentProfileId } from '@/config/agentProfiles'
import { resolveRecommendedModel } from '@/config/chatSectionProfiles'
import { getErrorMessage } from '@/utils/errors'
import { useAdminSections } from '@/hooks/useAdminSections'
import { matchAdminSection } from '@/types/adminSections'
import {
  BedrockAgentProfilePrompt,
  BedrockChatMessage,
  BedrockChatAttachment,
  BedrockChatSurface,
  BedrockPageContext,
  BedrockSessionType,
} from '@/types/bedrock'

const conversationsKey = (sessionType?: BedrockSessionType, agentProfileId?: string) =>
  ['bedrock', 'conversations', sessionType ?? 'all', agentProfileId ?? 'all'] as const

const messagesKey = (sessionId: string) => ['bedrock', 'conversations', sessionId, 'messages'] as const

export function useBedrockConversations(sessionType?: BedrockSessionType, agentProfileId?: string) {
  return useQuery({
    queryKey: conversationsKey(sessionType, agentProfileId),
    queryFn: () => bedrockApi.listConversations(sessionType, agentProfileId),
  })
}

export function useBedrockConversationMessages(sessionId: string) {
  return useQuery({
    queryKey: messagesKey(sessionId),
    queryFn: () => bedrockApi.getConversationMessages(sessionId),
    enabled: Boolean(sessionId),
  })
}

export interface UseBedrockChatOptions {
  chatSurface?: BedrockChatSurface
  pageContext?: BedrockPageContext | null
}

/**
 * Chat state + actions. Conversations/messages are server-persisted (see
 * api/bedrock.ts) - this hook wires ephemeral send/status/error state in
 * `bedrockChatStore` to React Query data and sends harness context
 * (page_context, model_id, chat_surface, agent_profile_id) on each turn.
 */
export function useBedrockChat(options: UseBedrockChatOptions = {}) {
  const chatSurface = options.chatSurface ?? 'contextual'
  const pageContext = options.pageContext ?? null
  const sessionType: BedrockSessionType = chatSurface === 'general' ? 'general' : 'contextual'

  const queryClient = useQueryClient()
  const getSessionPrefs = useBedrockChatStore((s) => s.getSessionPrefs)
  const isSending = useBedrockChatStore((s) => s.isSending)
  const statusMessage = useBedrockChatStore((s) => s.statusMessage)
  const error = useBedrockChatStore((s) => s.error)
  const newConversation = useBedrockChatStore((s) => s.newConversation)
  const switchConversation = useBedrockChatStore((s) => s.switchConversation)

  const { data: adminSections } = useAdminSections()
  const effectiveAgentProfileId = useMemo(() => {
    if (chatSurface === 'general') return AGENT_ORCHESTRATOR
    const match = matchAdminSection(pageContext?.route ?? '', adminSections ?? [])
    // feature 001: el chat contextual de una sección lo atiende su agente L2
    // asignado; si no tiene, el servidor degrada al orquestador.
    if (match?.section.agent_profile_id) {
      return match.section.agent_profile_id
    }
    return resolveAgentProfileId({ chatSurface, pageContext })
  }, [chatSurface, pageContext, adminSections])

  const bucketKey = conversationBucket(sessionType, effectiveAgentProfileId)
  const activeSessionId = useBedrockChatStore((s) => s.activeSessionIds[bucketKey] ?? '')

  useLayoutEffect(() => {
    useBedrockChatStore.getState().ensureSession(sessionType, effectiveAgentProfileId)
  }, [sessionType, effectiveAgentProfileId])

  const { data: conversations = [] } = useBedrockConversations(sessionType, effectiveAgentProfileId)
  const { data: messages = [] } = useBedrockConversationMessages(activeSessionId)
  const { data: modelStatus } = useBedrockModel()

  const send = async (text: string, attachments?: BedrockChatAttachment[]) => {
    const trimmed = text.trim()
    if ((!trimmed && !attachments?.length) || isSending || !activeSessionId) return

    const prefs = getSessionPrefs(activeSessionId)
    const recommended = resolveRecommendedModel(pageContext, modelStatus?.current_model_id)
    const allowed = new Set((modelStatus?.available_models ?? []).map((m) => m.model_id))
    const modelId =
      (prefs.modelIdOverride && allowed.has(prefs.modelIdOverride) && prefs.modelIdOverride) ||
      (recommended && allowed.has(recommended) && recommended) ||
      modelStatus?.current_model_id ||
      recommended

    const displayContent =
      trimmed || (attachments?.length ? `[${attachments.length} adjunto(s)]` : '')

    const optimisticMessage: BedrockChatMessage = {
      id: `optimistic-${Date.now()}`,
      role: 'user',
      content: displayContent,
      created_at: new Date().toISOString(),
    }
    queryClient.setQueryData<BedrockChatMessage[]>(messagesKey(activeSessionId), (old = []) => [
      ...old,
      optimisticMessage,
    ])

    useBedrockChatStore.setState({ isSending: true, statusMessage: null, error: null })

    try {
      await bedrockApi.chat(
        {
          session_id: activeSessionId,
          message: trimmed || '(adjuntos)',
          chat_surface: chatSurface,
          page_context: chatSurface === 'contextual' ? pageContext : null,
          model_id: modelId,
          agent_profile_id: chatSurface === 'contextual' ? effectiveAgentProfileId : null,
          attachments: attachments ?? null,
        },
        {
          onStatus: (message) => {
            useBedrockChatStore.setState({ statusMessage: message })
          },
        }
      )

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: messagesKey(activeSessionId) }),
        queryClient.invalidateQueries({ queryKey: ['bedrock', 'conversations'] }),
        invalidateAdminDataViews(queryClient),
      ])
      useBedrockChatStore.setState({ isSending: false, statusMessage: null })
    } catch (err) {
      useBedrockChatStore.setState({ isSending: false, statusMessage: null, error: getErrorMessage(err) })
    }
  }

  const renameMutation = useMutation({
    mutationFn: ({ sessionId, title }: { sessionId: string; title: string }) =>
      bedrockApi.renameConversation(sessionId, title),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['bedrock', 'conversations'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (sessionId: string) => bedrockApi.deleteConversation(sessionId),
    onSuccess: (_data, sessionId) => {
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'conversations'] })
      queryClient.removeQueries({ queryKey: messagesKey(sessionId) })
      if (sessionId === activeSessionId) newConversation(sessionType, effectiveAgentProfileId)
    },
  })

  return {
    sessionId: activeSessionId,
    sessionType,
    chatSurface,
    pageContext,
    effectiveAgentProfileId,
    messages,
    conversations,
    isSending,
    statusMessage,
    error,
    send,
    newConversation: () => newConversation(sessionType, effectiveAgentProfileId),
    switchConversation: (sessionId: string) =>
      switchConversation(sessionId, sessionType, effectiveAgentProfileId),
    renameConversation: (sessionId: string, title: string) => renameMutation.mutate({ sessionId, title }),
    deleteConversation: (sessionId: string) => deleteMutation.mutate(sessionId),
  }
}

export function useBedrockModel() {
  return useQuery({
    queryKey: ['bedrock', 'model'],
    queryFn: bedrockApi.getModel,
    retry: false,
  })
}

export function useBedrockModelSwitch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: bedrockApi.switchModel,
    onSuccess: (data) => {
      queryClient.setQueryData(['bedrock', 'model'], data)
    },
  })
}

export function useBedrockUsageMetrics(days = 30) {
  return useQuery({
    queryKey: ['bedrock', 'usage-metrics', days],
    queryFn: () => bedrockApi.usageMetrics(days),
  })
}

export function useBedrockInstructions() {
  return useQuery({
    queryKey: ['bedrock', 'instructions'],
    queryFn: bedrockApi.getInstructions,
  })
}

export function useBedrockInstructionsUpdate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: bedrockApi.updateInstructions,
    onSuccess: (data) => {
      queryClient.setQueryData(['bedrock', 'instructions'], data)
    },
  })
}

export function useBedrockGlobalRulesUpdate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: bedrockApi.updateGlobalRules,
    onSuccess: (data) => {
      queryClient.setQueryData(['bedrock', 'instructions'], data)
    },
  })
}

export function useBedrockAgentProfilePrompts() {
  return useQuery({
    queryKey: ['bedrock', 'agent-profiles'],
    queryFn: bedrockApi.listAgentProfilePrompts,
  })
}

export function useBedrockAgentProfilePromptUpdate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      profileId,
      systemPromptSuffix,
    }: {
      profileId: string
      systemPromptSuffix: string | null
    }) => bedrockApi.updateAgentProfilePrompt(profileId, systemPromptSuffix),
    onSuccess: (data) => {
      queryClient.setQueryData<BedrockAgentProfilePrompt[]>(['bedrock', 'agent-profiles'], (prev) => {
        if (!prev) return [data]
        return prev.map((p) => (p.profile_id === data.profile_id ? data : p))
      })
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-catalog'] })
    },
  })
}

export function useBedrockTools() {
  return useQuery({
    queryKey: ['bedrock', 'tools'],
    queryFn: bedrockApi.listTools,
  })
}

export function useBedrockToolMutations() {
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['bedrock', 'tools'] })

  const createMutation = useMutation({
    mutationFn: bedrockApi.createTool,
    onSuccess: invalidate,
  })
  const setEnabledMutation = useMutation({
    mutationFn: ({ id, isEnabled }: { id: string; isEnabled: boolean }) => bedrockApi.setToolEnabled(id, isEnabled),
    onSuccess: invalidate,
  })
  const deleteMutation = useMutation({
    mutationFn: bedrockApi.deleteTool,
    onSuccess: invalidate,
  })

  return { createMutation, setEnabledMutation, deleteMutation }
}

export function useBedrockMemoryEvents(sessionId: string | null) {
  return useQuery({
    queryKey: ['bedrock', 'memory', 'events', sessionId],
    queryFn: () => bedrockApi.getMemoryEvents(sessionId as string),
    enabled: !!sessionId,
  })
}

export function useBedrockMemoryRecords(query: string) {
  return useQuery({
    queryKey: ['bedrock', 'memory', 'records', query],
    queryFn: () => bedrockApi.getMemoryRecords(query),
    enabled: query.trim().length > 0,
  })
}

export function useBedrockManualMemory() {
  return useMutation({ mutationFn: bedrockApi.addManualMemory })
}

export function useBedrockAuditLog(limit = 50) {
  return useQuery({
    queryKey: ['bedrock', 'audit-log', limit],
    queryFn: () => bedrockApi.getAuditLog(limit),
  })
}

export function useBedrockAuditRestore() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: bedrockApi.restoreAuditEntry,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'audit-log'] })
    },
  })
}

export function useAgentTasks() {
  return useQuery({
    queryKey: ['agent-tasks'],
    queryFn: agentTasksApi.list,
    refetchInterval: (query) =>
      query.state.data?.some((task) => task.status === 'in_progress') ? 4000 : false,
  })
}

export function useAgentTaskMutations() {
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['agent-tasks'] })

  const createMutation = useMutation({ mutationFn: agentTasksApi.create, onSuccess: invalidate })
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof agentTasksApi.update>[1] }) =>
      agentTasksApi.update(id, payload),
    onSuccess: invalidate,
  })
  const deleteMutation = useMutation({ mutationFn: agentTasksApi.remove, onSuccess: invalidate })
  const runMutation = useMutation({ mutationFn: agentTasksApi.run, onSuccess: invalidate })

  return { createMutation, updateMutation, deleteMutation, runMutation }
}

export function useAgentCatalog() {
  return useQuery({
    queryKey: ['bedrock', 'agent-catalog'],
    queryFn: bedrockApi.listAgentCatalog,
  })
}

export function useAgentCatalogItem(profileId: string | undefined) {
  return useQuery({
    queryKey: ['bedrock', 'agent-catalog', profileId],
    queryFn: () => bedrockApi.getAgentCatalogItem(profileId as string),
    enabled: Boolean(profileId),
  })
}

export function useAgentMethodologiesUpdate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ profileId, methodologyIds }: { profileId: string; methodologyIds: string[] }) =>
      bedrockApi.updateAgentMethodologies(profileId, methodologyIds),
    onSuccess: (_data, { profileId }) => {
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-catalog'] })
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-catalog', profileId] })
    },
  })
}

export function useAgentToolsUpdate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ profileId, toolNames }: { profileId: string; toolNames: string[] | null }) =>
      bedrockApi.updateAgentTools(profileId, toolNames),
    onSuccess: (_data, { profileId }) => {
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-catalog'] })
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-catalog', profileId] })
    },
  })
}

export function useBedrockToolsCatalog() {
  return useQuery({
    queryKey: ['bedrock', 'tools-catalog'],
    queryFn: bedrockApi.listToolsCatalog,
  })
}

export function useAgentDelegationUpdate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ profileId, targetIds }: { profileId: string; targetIds: string[] | null }) =>
      bedrockApi.updateAgentDelegation(profileId, targetIds),
    onSuccess: (_data, { profileId }) => {
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-catalog'] })
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-catalog', profileId] })
    },
  })
}

export function useAgentSectionsUpdate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ profileId, sectionIds }: { profileId: string; sectionIds: string[] }) =>
      bedrockApi.updateAgentSections(profileId, sectionIds),
    onSuccess: (_data, { profileId }) => {
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-catalog'] })
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-catalog', profileId] })
      queryClient.invalidateQueries({ queryKey: ['admin', 'sections'] })
    },
  })
}

export function useAgentPhotoUpdate() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ profileId, photoUrl }: { profileId: string; photoUrl: string | null }) =>
      bedrockApi.updateAgentPhoto(profileId, photoUrl),
    onSuccess: (_data, { profileId }) => {
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-catalog'] })
      queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-catalog', profileId] })
    },
  })
}

export function useAgentMemory(profileId: string | undefined) {
  return useQuery({
    queryKey: ['bedrock', 'agent-memory', profileId],
    queryFn: () => bedrockApi.getAgentMemory(profileId as string),
    enabled: Boolean(profileId),
  })
}

export function useAgentMemoryNoteMutations(profileId: string) {
  const queryClient = useQueryClient()
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['bedrock', 'agent-memory', profileId] })
  return {
    add: useMutation({
      mutationFn: (text: string) => bedrockApi.addAgentMemoryNote(profileId, text),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (noteId: string) => bedrockApi.deleteAgentMemoryNote(profileId, noteId),
      onSuccess: invalidate,
    }),
  }
}
