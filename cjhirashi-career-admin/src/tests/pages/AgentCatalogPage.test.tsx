import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen, waitFor, fireEvent } from '../utils'
import { AgentCatalogPage } from '@/pages/AgentCatalogPage'
import { bedrockApi } from '@/api/bedrock'
import { adminSectionsApi } from '@/api/adminSections'
import { BedrockAgentCatalogItem } from '@/types/bedrock'

vi.mock('@/api/bedrock')
vi.mock('@/api/adminSections')
vi.mock('@/api/files', () => ({
  filesApi: {
    list: vi.fn().mockResolvedValue([]),
    upload: vi.fn(),
    setVisibility: vi.fn(),
    getDownloadUrl: vi.fn(),
  },
}))

const mockedApi = vi.mocked(bedrockApi)
const mockedSections = vi.mocked(adminSectionsApi)

const catalogFields = {
  sections: [
    {
      id: 'pdf-templates',
      label: 'Plantillas PDF',
      section_type: 'table',
      path: '/agent/pdf-templates',
    },
  ],
  delegation_targets: [{ id: 'agent_pdf_render', label: 'Renderizado PDF', level: 3 }],
  delegation_target_ids: ['agent_pdf_render'],
  default_delegation_target_ids: ['agent_pdf_render', 'agent_changelog'],
  allowed_delegation_ids: ['agent_pdf_render', 'agent_changelog'],
  delegation_is_default: true,
}

const sampleAgent: BedrockAgentCatalogItem = {
  id: 'agent-8',
  system_name: 'agent_pdf_design',
  profile_id: 'agent_pdf_design',
  label: 'Diseño PDF',
  level: 2,
  user_facing: true,
  can_delegate: true,
  write_enabled: true,
  domain_keys: ['document_output'],
  resource_keys: ['pdf-output-templates', 'pdf-template-styles'],
  default_model_id: 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
  tools: ['pdf_style', 'pdf_template', 'search_knowledge_base', 'delegate_to_specialist'],
  default_tools: ['pdf_style', 'pdf_template', 'search_knowledge_base', 'delegate_to_specialist'],
  override_tools: null,
  effective_tools: ['pdf_style', 'pdf_template', 'search_knowledge_base', 'delegate_to_specialist'],
  has_own_memory: true,
  default_suffix: 'Eres PDF Maker',
  override_suffix: null,
  effective_suffix: 'Eres PDF Maker',
  prompt_is_default: true,
  methodology_count: 1,
  assigned_methodologies: [
    { id: 'opm-1', title: 'Plantillas PDF', section: 'Diseño PDF', shared: false, assigned: true },
    { id: 'opm-2', title: 'Otra', section: null, shared: true, assigned: true },
  ],
  methodologies: [
    { id: 'opm-1', title: 'Plantillas PDF', section: 'Diseño PDF', shared: false, assigned: true },
    { id: 'opm-2', title: 'Otra', section: null, shared: true, assigned: true },
  ],
  conversation_count: 2,
  ...catalogFields,
}

const l3Agent: BedrockAgentCatalogItem = {
  ...sampleAgent,
  id: 'agent-9',
  system_name: 'agent_pdf_render',
  profile_id: 'agent_pdf_render',
  label: 'Renderizado PDF',
  level: 3,
  user_facing: false,
  can_delegate: false,
  has_own_memory: false,
  resource_keys: ['cv-versions', 'cover-letter-versions'],
  tools: ['generate_pdf', 'render_record_pdf'],
  methodology_count: 0,
  assigned_methodologies: [],
  conversation_count: 0,
  sections: [],
  delegation_targets: [],
  delegation_target_ids: [],
  default_delegation_target_ids: [],
  allowed_delegation_ids: [],
}

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/settings/agents/:profileId?" element={<AgentCatalogPage />} />
      </Routes>
    </MemoryRouter>
  )

describe('AgentCatalogPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.listAgentCatalog.mockResolvedValue([sampleAgent, l3Agent])
    mockedApi.getAgentCatalogItem.mockResolvedValue(sampleAgent)
    mockedApi.getAgentMemory.mockResolvedValue({
      has_own_memory: true,
      conversation_count: 2,
      notes: [{ id: '11', text: 'Usar paleta cyan' }],
    })
    mockedApi.listConversations.mockResolvedValue([])
    mockedApi.listToolsCatalog.mockResolvedValue({
      builtin: [
        { name: 'pdf_template', description: 'CRUD de plantillas' },
        { name: 'pdf_style', description: 'CRUD de estilos' },
        { name: 'search_knowledge_base', description: 'Búsqueda semántica' },
      ],
      mcp: [],
    })
    mockedSections.list.mockResolvedValue([
      {
        id: 'sec-16',
        system_name: 'settings-agents',
        label: 'Catálogo de Agentes',
        path: '/settings/agents',
        section_type: 'table',
        group: 'Settings',
        resource_key: null,
        related_tools: [],
        default_agent_profile_id: 'agent_configuration',
        agent_profile_id: 'agent_configuration',
        agent_label: 'Configuración',
        agent_is_default: true,
        sidebar_has_chat: true,
        sidebar_has_instructions: true,
        view_count: 3,
        views: [
          {
            key: 'list',
            label: 'Lista',
            description: 'Tabla',
            sidebar_title: 'Agentes',
            sidebar_body: 'No se pueden crear ni eliminar.',
            is_default: true,
          },
          {
            key: 'view',
            label: 'Vista',
            description: 'Detalle',
            sidebar_title: 'Agentes',
            sidebar_body: 'Revisa el registro.',
            is_default: false,
          },
          {
            key: 'edit',
            label: 'Edición',
            description: 'Formulario',
            sidebar_title: 'Agentes',
            sidebar_body: 'Edita overrides.',
            is_default: false,
          },
        ],
      },
    ])
  })

  it('lists agents with table-section chrome and no create action', async () => {
    renderAt('/settings/agents')
    await waitFor(() => expect(screen.getByText('Diseño PDF')).toBeInTheDocument())
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Lista' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Vista' }).tagName).not.toBe('BUTTON')
    expect(screen.getByRole('tab', { name: 'Edición' }).tagName).not.toBe('BUTTON')
    expect(screen.getByPlaceholderText(/buscar en catálogo de agentes/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Nuevo' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Eliminar' })).not.toBeInTheDocument()
    expect(screen.getByText('agent-8')).toBeInTheDocument()
    expect(screen.getByText('agent_pdf_design')).toBeInTheDocument()
    expect(screen.getByText('Renderizado PDF')).toBeInTheDocument()
    expect(screen.getByText('2 chats')).toBeInTheDocument()
  })

  it('opens Vista from a row and Edición from the edit button', async () => {
    renderAt('/settings/agents')
    await waitFor(() => expect(screen.getByText('Diseño PDF')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Diseño PDF'))
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Vista' })).toHaveAttribute('aria-selected', 'true'))
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Catálogo de Agentes')
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('agent-8')
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Diseño PDF')
    expect(screen.getByText('pdf_style')).toBeInTheDocument()
    expect(screen.getByText('Foto')).toBeInTheDocument()
    expect(screen.queryByLabelText('Prompt del especialista')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Edición' }))
    expect(screen.getByRole('tab', { name: 'Vista' })).toHaveAttribute('aria-selected', 'true')

    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Edición' })).toHaveAttribute('aria-selected', 'true'))
    expect(screen.getAllByText('Editable').length).toBeGreaterThan(0)
    await waitFor(() =>
      expect(screen.getByLabelText('Prompt del especialista')).toHaveValue('Eres PDF Maker')
    )
    expect(screen.getByRole('button', { name: /guardar prompt/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /guardar metodologías/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /guardar secciones/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /guardar delegación/i })).toBeInTheDocument()
    expect(screen.getByText('Usar paleta cyan')).toBeInTheDocument()
    expect(screen.getByText(/elige una imagen del bucket/i)).toBeInTheDocument()
  })

  it('tells L3 agents they have no own memory', async () => {
    mockedApi.getAgentCatalogItem.mockResolvedValue(l3Agent)
    mockedApi.getAgentMemory.mockResolvedValue({
      has_own_memory: false,
      conversation_count: 0,
      notes: [],
    })
    renderAt('/settings/agents/agent-9')
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Renderizado PDF')
    )
    expect(screen.getByText(/no tienen chat ni memoria propia/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Edición' })).toHaveAttribute('aria-selected', 'true'))
    expect(screen.getByText(/no tienen chat ni memoria propia/i)).toBeInTheDocument()
    expect(screen.queryByLabelText('Nueva nota de memoria')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /guardar delegación/i })).not.toBeInTheDocument()
  })

  it('saves a prompt override from Edición', async () => {
    mockedApi.updateAgentProfilePrompt.mockResolvedValue({
      profile_id: 'agent_pdf_design',
      label: 'Diseño PDF',
      default_suffix: 'Eres PDF Maker',
      override_suffix: 'Custom',
      effective_suffix: 'Custom',
      is_default: false,
    })
    renderAt('/settings/agents/agent-8')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Editar' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }))
    await waitFor(() => expect(screen.getByLabelText('Prompt del especialista')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Prompt del especialista'), { target: { value: 'Custom' } })
    fireEvent.click(screen.getByRole('button', { name: /guardar prompt/i }))
    await waitFor(() =>
      expect(mockedApi.updateAgentProfilePrompt).toHaveBeenCalledWith('agent_pdf_design', 'Custom')
    )
  })

  it('filters the list from the search box', async () => {
    renderAt('/settings/agents')
    await waitFor(() => expect(screen.getByText('Diseño PDF')).toBeInTheDocument())
    fireEvent.change(screen.getByPlaceholderText(/buscar en catálogo de agentes/i), {
      target: { value: 'Renderizado' },
    })
    await waitFor(() => expect(screen.queryByText('Diseño PDF')).not.toBeInTheDocument())
    expect(screen.getByText('Renderizado PDF')).toBeInTheDocument()
  })
})
