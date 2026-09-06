import React, { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Pencil, RotateCcw, Save, Trash2 } from 'lucide-react'
import { agentCatalogConfig, catalogAgentMatches, catalogItemToRow } from '@/config/agentCatalogResource'
import { FieldConfig } from '@/config/careerResources'
import { CareerEntity } from '@/types/career'
import { ListFilters } from '@/api/career'
import { useSectionViewTabs } from '@/components/SectionViewTabs'
import { ColumnFilterButton, isFilterableField } from '@/components/career/ResourceListFilters'
import { StatusIndicator } from '@/components/StatusIndicator'
import { ThemedMultiSelect } from '@/components/ThemedMultiSelect'
import { LoadingSpinner } from '@/components/LoadingSpinner'
import { useVisibleTableColumns } from '@/hooks/useVisibleTableColumns'
import { SectionShell, SectionToolbar, SectionTable, SectionTableFooter } from '@/components/section'
import {
  useAgentCatalog,
  useAgentCatalogItem,
  useAgentDelegationUpdate,
  useAgentMemory,
  useAgentMemoryNoteMutations,
  useAgentMethodologiesUpdate,
  useAgentPhotoUpdate,
  useAgentSectionsUpdate,
  useAgentToolsUpdate,
  useBedrockAgentProfilePromptUpdate,
  useBedrockConversations,
  useBedrockToolsCatalog,
} from '@/hooks/useBedrockChat'
import { useAdminSections } from '@/hooks/useAdminSections'
import { getErrorMessage } from '@/utils/errors'
import { hasActiveFilters, recordMatchesFilters } from '@/utils/listFilters'
import {
  availableTableColumns,
  defaultTableColumns,
  pinnedColumnKeys,
} from '@/utils/tableColumns'
import { recordSegmentFromPath } from '@/utils/recordUrl'
import { ADMIN_SECTION_TYPE_LABEL } from '@/types/adminSections'
import { BedrockAgentCatalogItem } from '@/types/bedrock'
import { allAgentSelectOptions } from '@/config/agentProfiles'
import { PersonChip } from '@/components/PersonAvatar'
import { BucketImagePicker } from '@/components/BucketImagePicker'

const LIST_PATH = '/settings/agents'
const PAGE_SIZE = 20

const LIST_VIEW_TABS = [
  { key: 'list', label: 'Lista' },
  { key: 'view', label: 'Vista' },
  { key: 'edit', label: 'Edición' },
]

type ViewState = 'list' | 'view' | 'edit'

const Badge: React.FC<{ color: 'cyan' | 'slate' | 'success' | 'error' | 'warning'; children: React.ReactNode }> = ({
  color,
  children,
}) => <span className={`badge badge-${color}`}>{children}</span>

const fieldForColumn = (columnKey: string): FieldConfig | undefined =>
  agentCatalogConfig.fields.find((field) => field.name === columnKey)

const compareValues = (a: unknown, b: unknown): number => {
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b)
  return String(a).localeCompare(String(b), 'es', { numeric: true, sensitivity: 'base' })
}

const rowMatchesSearch = (row: CareerEntity, query: string): boolean => {
  if (!query) return true
  const needle = query.toLowerCase()
  const haystack = [
    row.label,
    row.id,
    row.profile_id,
    row.system_name,
    ...(Array.isArray(row.domain_keys) ? row.domain_keys : []),
  ]
  return haystack.some((part) => String(part ?? '').toLowerCase().includes(needle))
}

const ChipList: React.FC<{ items: string[]; empty: string }> = ({ items, empty }) => {
  if (!items.length) {
    return <p className="text-sm text-text-secondary">{empty}</p>
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span key={item} className="badge">
          {item}
        </span>
      ))}
    </div>
  )
}

const FieldBadge: React.FC<{ editable?: boolean }> = ({ editable }) => (
  <span className={`badge ${editable ? 'badge-cyan' : ''}`}>{editable ? 'Editable' : 'Monitoreo'}</span>
)

const IconAction: React.FC<{
  label: string
  disabled?: boolean
  muted?: boolean
  onClick: () => void
  children: React.ReactNode
}> = ({ label, disabled, muted, onClick, children }) => (
  <button
    type="button"
    className={`btn-icon btn-icon-sm${muted ? ' btn-icon-muted' : ''}`}
    aria-label={label}
    title={label}
    disabled={disabled}
    onClick={onClick}
  >
    {children}
  </button>
)

const EditorBlock: React.FC<{
  title: string
  editable?: boolean
  actions?: React.ReactNode
  children: React.ReactNode
}> = ({ title, editable, actions, children }) => (
  <div className="space-y-3">
    <div className="flex items-center gap-2 min-w-0">
      <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide flex items-center gap-2 min-w-0">
        {title}
        <FieldBadge editable={editable} />
      </h3>
      {actions ? <div className="ml-auto flex items-center gap-1 flex-shrink-0">{actions}</div> : null}
    </div>
    {children}
  </div>
)

export const AgentCatalogPage: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { profileId: routeProfileId } = useParams<{ profileId?: string }>()
  const recordSegment = recordSegmentFromPath(location.pathname, LIST_PATH)
  const profileId = routeProfileId || recordSegment || ''

  const sectionViews = useSectionViewTabs(LIST_VIEW_TABS)
  const { data: catalog = [], isLoading, isError, error, refetch } = useAgentCatalog()
  const detailQuery = useAgentCatalogItem(profileId)
  const rows = useMemo(() => catalog.map(catalogItemToRow), [catalog])

  const [viewState, setViewState] = useState<ViewState>(profileId ? 'view' : 'list')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<string | undefined>(undefined)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [filters, setFilters] = useState<ListFilters>({})
  const [skip, setSkip] = useState(0)

  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput.trim()), 300)
    return () => clearTimeout(timer)
  }, [searchInput])

  const filtersActive = hasActiveFilters(filters)
  const availableCols = useMemo(() => availableTableColumns(agentCatalogConfig), [])
  const defaultColKeys = useMemo(
    () => defaultTableColumns(agentCatalogConfig).map((col) => col.key),
    []
  )
  const pinnedCols = useMemo(() => pinnedColumnKeys(agentCatalogConfig), [])
  const {
    columns: displayColumns,
    selectedKeys: visibleColumnKeys,
    toggleColumn,
    moveColumn,
    pinnedKeys: pinnedColumnIds,
    options: columnOptions,
  } = useVisibleTableColumns(agentCatalogConfig.key, availableCols, defaultColKeys, pinnedCols)

  const toggleSort = (key: string) => {
    setSkip(0)
    setSortBy((current) => {
      if (current !== key) {
        setSortDir('asc')
        return key
      }
      setSortDir((dir) => (dir === 'asc' ? 'desc' : 'asc'))
      return key
    })
  }

  useEffect(() => {
    setSkip(0)
  }, [search, sortBy, sortDir, filters])

  const filteredRows = useMemo(() => {
    const matched = rows.filter(
      (row) => rowMatchesSearch(row, search) && recordMatchesFilters(row, filtersActive ? filters : undefined)
    )
    if (!sortBy) return matched
    const copy = [...matched]
    copy.sort((a, b) => {
      const result = compareValues(a[sortBy], b[sortBy])
      return sortDir === 'asc' ? result : -result
    })
    return copy
  }, [rows, search, filters, filtersActive, sortBy, sortDir])

  const totalCount = filteredRows.length
  const pageRows = filteredRows.slice(skip, skip + PAGE_SIZE)

  useEffect(() => {
    if (!profileId) {
      setViewState('list')
      return
    }
    setViewState((current) => (current === 'list' ? 'view' : current))
  }, [profileId])

  const openView = (item: CareerEntity) => {
    setViewState('view')
    const next = `${LIST_PATH}/${item.id}`
    if (location.pathname !== next) navigate(next)
  }

  const openEdit = (item: CareerEntity) => {
    setViewState('edit')
    const next = `${LIST_PATH}/${item.id}`
    if (location.pathname !== next) navigate(next)
  }

  const backToList = () => {
    setViewState('list')
    if (location.pathname !== LIST_PATH) navigate(LIST_PATH)
  }

  const cancelForm = () => setViewState('view')

  const activeViewKey = viewState === 'list' ? 'list' : viewState === 'view' ? 'view' : 'edit'
  const selectSectionView = (key: string) => {
    if (key === 'list' && viewState !== 'list') backToList()
  }

  const headingRecord =
    viewState === 'list'
      ? null
      : pageRows.concat(rows).find(
          (row) =>
            String(row.id) === profileId ||
            String(row.system_name ?? '') === profileId ||
            String(row.profile_id ?? '') === profileId
        ) ??
        (detailQuery.data ? catalogItemToRow(detailQuery.data) : null)
  const headingName = headingRecord && typeof headingRecord.label === 'string' ? headingRecord.label : ''
  const showRecordHeading = viewState !== 'list' && Boolean(headingRecord)
  const headingText = agentCatalogConfig.label

  const headerActions =
    viewState === 'view' && headingRecord ? (
      <button
        type="button"
        onClick={() => openEdit(headingRecord)}
        className="btn-icon btn-icon-sm"
        aria-label="Editar"
        title="Editar"
      >
        <Pencil size={13} />
      </button>
    ) : null

  const listColumn = (key: string) => displayColumns.find((col) => col.key === key)

  const renderCell = (item: CareerEntity, key: string): React.ReactNode | undefined => {
    const value = item[key]
    if (key === 'label') {
      return (
        <PersonChip
          src={typeof item.photo_url === 'string' ? item.photo_url : null}
          name={String(item.label ?? '')}
        />
      )
    }
    const col = listColumn(key)
    const field = fieldForColumn(key)
    if (col?.format === 'boolean' || field?.type === 'boolean') {
      return <StatusIndicator active={Boolean(value)} />
    }
    if (col?.format === 'badge' && value !== null && value !== undefined && value !== '') {
      const label = field?.options?.find((opt) => opt.value === String(value))?.label ?? String(value)
      return <Badge color={col.badgeColor ? col.badgeColor(value) : 'slate'}>{label}</Badge>
    }
    return undefined
  }

  const headerExtra = (key: string): React.ReactNode => {
    const field = fieldForColumn(key)
    return isFilterableField(field) ? (
      <ColumnFilterButton
        resourceKey={agentCatalogConfig.key}
        field={field}
        value={filters}
        onChange={setFilters}
      />
    ) : null
  }

  return (
    <SectionShell
      title={headingText}
      count={viewState === 'list' ? totalCount : undefined}
      breadcrumb={
        showRecordHeading && headingRecord
          ? { section: headingText, id: headingRecord.id, name: headingName }
          : undefined
      }
      tabs={sectionViews}
      activeTab={activeViewKey}
      interactiveTabs={['list']}
      onTabSelect={selectSectionView}
      actions={headerActions}
      variant={viewState === 'list' ? 'list' : 'record'}
    >
      <>
          {viewState === 'view' && (
            <AgentCatalogRecordView
              profileId={profileId}
              fallback={catalog.find((agent) => catalogAgentMatches(agent, profileId))}
              catalogError={isError ? error : null}
            />
          )}

          {viewState === 'edit' && (
            <AgentCatalogEditors
              profileId={profileId}
              fallback={catalog.find((agent) => catalogAgentMatches(agent, profileId))}
              onCancel={cancelForm}
            />
          )}

          {viewState === 'list' && (
            <>
              <SectionToolbar
                search={{
                  value: searchInput,
                  onChange: setSearchInput,
                  placeholder: `Buscar en ${agentCatalogConfig.label.toLowerCase()}...`,
                }}
                filtersActive={filtersActive}
                onClearFilters={() => setFilters({})}
                columnSettings={{
                  options: columnOptions,
                  value: visibleColumnKeys,
                  pinnedKeys: pinnedColumnIds,
                  onToggle: toggleColumn,
                  onMove: moveColumn,
                }}
              />

              <SectionTable<CareerEntity>
                columns={displayColumns}
                rows={pageRows}
                getRowKey={(item) => String(item.id)}
                sort={sortBy ? { key: sortBy, dir: sortDir } : undefined}
                onToggleSort={toggleSort}
                onRowClick={openView}
                renderCell={renderCell}
                headerExtra={headerExtra}
                rowActions={(item) => (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      openEdit(item)
                    }}
                    aria-label="Editar"
                    className="p-1.5 rounded text-text-secondary hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-cyan-600"
                  >
                    <Pencil size={15} />
                  </button>
                )}
                state={{
                  isLoading,
                  isError,
                  errorMessage: isError ? getErrorMessage(error) : undefined,
                  onRetry: refetch,
                }}
                emptyMessage={
                  search || filtersActive
                    ? 'Sin resultados para esa búsqueda o filtros.'
                    : `No hay ${agentCatalogConfig.label.toLowerCase()} todavía.`
                }
              />

              {!isLoading && !isError && (
                <SectionTableFooter
                  variant="pager"
                  page={Math.floor(skip / PAGE_SIZE) + 1}
                  hasMore={skip + pageRows.length < totalCount}
                  onPageChange={(p) => setSkip((p - 1) * PAGE_SIZE)}
                  shown={pageRows.length}
                  pageSize={PAGE_SIZE}
                  total={totalCount}
                />
              )}
            </>
          )}
      </>
    </SectionShell>
  )
}

const AgentCatalogRecordView: React.FC<{
  profileId: string
  fallback?: BedrockAgentCatalogItem
  catalogError: unknown
}> = ({ profileId, fallback, catalogError }) => {
  const { data, isLoading, isError, error } = useAgentCatalogItem(profileId)
  const { data: memory } = useAgentMemory(profileId)
  const agent = data ?? fallback

  if (!agent && isLoading) {
    return <LoadingSpinner fullScreen={false} message="Cargando agente..." />
  }
  if (!agent && (isError || catalogError)) {
    return (
      <p className="text-red-600 dark:text-red-400 text-sm">
        {getErrorMessage(error ?? catalogError)}
      </p>
    )
  }
  if (!agent) {
    return <p className="text-text-secondary">Agente no encontrado.</p>
  }

  const conversationCount = memory?.conversation_count ?? agent.conversation_count
  const notes = memory?.notes ?? []

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-3">Información</h3>
        <dl className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <dt className="text-xs text-text-secondary mb-1">Foto</dt>
            <dd>
              <PersonChip src={agent.photo_url} name={agent.label} size={36} />
            </dd>
          </div>
          <ViewField label="Agente" value={agent.label} />
          <ViewField label="ID" value={agent.id} mono />
          <ViewField label="Nombre sistema" value={agent.system_name || agent.profile_id} mono />
          <ViewField label="Nivel" value={`L${agent.level}`} />
          <ViewField label="Chat" value={agent.user_facing ? 'Sí' : 'No (L3)'} />
          <ViewField label="Delega" value={agent.can_delegate ? 'Sí' : 'No'} />
          <ViewField label="Escritura" value={agent.write_enabled ? 'Habilitada' : 'Solo lectura'} />
          <ViewField label="Dominio" value={agent.domain_keys.join(', ') || '—'} />
          <ViewField label="Modelo default" value={agent.default_model_id || '—'} mono />
          <ViewField
            label="Prompt"
            value={agent.prompt_is_default ? 'Default (código)' : 'Override'}
          />
          <ViewField
            label="Destinos de delegación"
            value={
              agent.can_delegate
                ? agent.delegation_is_default
                  ? 'Por nivel'
                  : `${agent.delegation_target_ids.length} destinos`
                : '—'
            }
          />
        </dl>
      </div>

      <div>
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-3">Secciones</h3>
        <ChipList
          items={(agent.sections ?? []).map((row) => row.label)}
          empty="Ninguna sección asignada."
        />
      </div>

      <div>
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-3">Herramientas</h3>
        <ChipList items={agent.tools} empty="Sin tools." />
      </div>

      <div>
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-3">Metodologías</h3>
        <ChipList
          items={(agent.assigned_methodologies ?? agent.methodologies?.filter((row) => row.assigned) ?? []).map(
            (row) => row.title
          )}
          empty="Ninguna metodología asignada."
        />
      </div>

      <div>
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-3">Prompt de sistema</h3>
        <pre className="p-3 rounded-xl bg-glass whitespace-pre-wrap font-mono text-[11px] text-text">
          {agent.effective_suffix || '—'}
        </pre>
      </div>

      <div>
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-3">Memoria</h3>
        {!agent.has_own_memory ? (
          <p className="text-sm text-text-secondary">
            Los agentes L3 no tienen chat ni memoria propia. El L1/L2 que los invoca resume el
            resultado de la tarea.
          </p>
        ) : (
          <div className="space-y-2">
            <p className="text-sm text-text">
              {conversationCount} conversación{conversationCount === 1 ? '' : 'es'}
            </p>
            {notes.length > 0 && (
              <ul className="space-y-1">
                {notes.map((note) => (
                  <li key={note.id} className="text-sm text-text-secondary whitespace-pre-wrap">
                    {note.text}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

const ViewField: React.FC<{ label: string; value: string; mono?: boolean }> = ({ label, value, mono }) => (
  <div>
    <dt className="text-xs text-text-secondary mb-1">{label}</dt>
    <dd className={`text-sm text-text ${mono ? 'font-mono text-xs break-all' : ''}`}>{value}</dd>
  </div>
)

const AgentCatalogEditors: React.FC<{
  profileId: string
  fallback?: BedrockAgentCatalogItem
  onCancel: () => void
}> = ({ profileId, fallback, onCancel }) => {
  const { data: fetched, isLoading, isError, error } = useAgentCatalogItem(profileId)
  const data = fetched ?? fallback
  const { data: memory } = useAgentMemory(profileId)
  const { data: conversations = [] } = useBedrockConversations(undefined, profileId)
  const { data: allSections = [] } = useAdminSections()
  const promptUpdate = useBedrockAgentProfilePromptUpdate()
  const methodologiesUpdate = useAgentMethodologiesUpdate()
  const delegationUpdate = useAgentDelegationUpdate()
  const sectionsUpdate = useAgentSectionsUpdate()
  const photoUpdate = useAgentPhotoUpdate()
  const toolsUpdate = useAgentToolsUpdate()
  const { data: toolsCatalog } = useBedrockToolsCatalog()
  const notes = useAgentMemoryNoteMutations(profileId)
  const [promptDraft, setPromptDraft] = useState('')
  const [selectedMethodologyIds, setSelectedMethodologyIds] = useState<string[]>([])
  const [selectedSectionIds, setSelectedSectionIds] = useState<string[]>([])
  const [selectedDelegateIds, setSelectedDelegateIds] = useState<string[]>([])
  const [selectedToolNames, setSelectedToolNames] = useState<string[]>([])
  const [noteDraft, setNoteDraft] = useState('')

  useEffect(() => {
    if (data) {
      setPromptDraft(data.effective_suffix)
      const source = data.methodologies ?? data.assigned_methodologies
      setSelectedMethodologyIds(source.filter((row) => row.assigned).map((row) => row.id))
      setSelectedSectionIds((data.sections ?? []).map((row) => row.id))
      setSelectedDelegateIds(data.delegation_target_ids ?? [])
      const editableDefault = (data.default_tools ?? []).filter((t) => t !== 'delegate_to_specialist')
      const editableOverride =
        data.override_tools === null
          ? null
          : data.override_tools.filter((t) => t !== 'delegate_to_specialist')
      setSelectedToolNames((editableOverride ?? editableDefault).slice().sort())
    }
  }, [data])

  const methodologyOptions = useMemo(
    () =>
      (data?.methodologies ?? []).map((row) => ({
        value: row.id,
        label: row.shared ? `${row.title} (compartida)` : row.title,
      })),
    [data]
  )

  const sectionOptions = useMemo(
    () =>
      allSections.map((row) => ({
        value: row.id,
        label: `${row.label} · ${row.system_name} (${
          ADMIN_SECTION_TYPE_LABEL[row.section_type] ?? row.section_type
        })`,
      })),
    [allSections]
  )

  const delegateOptions = useMemo(() => {
    const allowed = new Set(data?.allowed_delegation_ids ?? data?.default_delegation_target_ids ?? [])
    return allAgentSelectOptions().filter((opt) => allowed.has(opt.value))
  }, [data])

  const toolOptions = useMemo(
    () =>
      (toolsCatalog?.builtin ?? [])
        .filter((t) => t.name !== 'delegate_to_specialist')
        .map((t) => ({ value: t.name, label: t.name })),
    [toolsCatalog]
  )

  const promptDirty = data !== undefined && promptDraft !== data.effective_suffix
  const assignedIds = (data?.methodologies ?? data?.assigned_methodologies ?? [])
    .filter((row) => row.assigned)
    .map((row) => row.id)
    .sort()
    .join(',')
  const methodologyDirty = selectedMethodologyIds.slice().sort().join(',') !== assignedIds
  const sectionDirty =
    selectedSectionIds.slice().sort().join(',') !==
    (data?.sections ?? []).map((row) => row.id).sort().join(',')
  const delegationDirty =
    selectedDelegateIds.slice().sort().join(',') !==
    (data?.delegation_target_ids ?? []).slice().sort().join(',')
  const toolsEditableDefault = (data?.default_tools ?? []).filter((t) => t !== 'delegate_to_specialist')
  const toolsEditableOverride =
    data?.override_tools === null
      ? null
      : (data?.override_tools ?? []).filter((t) => t !== 'delegate_to_specialist')
  const toolsInitial = (toolsEditableOverride ?? toolsEditableDefault).slice().sort().join(',')
  const toolsDirty = selectedToolNames.slice().sort().join(',') !== toolsInitial

  if (!data && isLoading) {
    return <LoadingSpinner fullScreen={false} message="Cargando agente..." />
  }
  if (!data && isError) {
    return <p className="text-red-600 dark:text-red-400 text-sm">{getErrorMessage(error)}</p>
  }
  if (!data) {
    return <p className="text-text-secondary">Agente no encontrado.</p>
  }

  return (
    <div className="space-y-8">
      <EditorBlock title="Foto" editable>
        <BucketImagePicker
          value={data.photo_url}
          name={data.label}
          onChange={(url) => photoUpdate.mutate({ profileId: data.profile_id, photoUrl: url })}
          disabled={photoUpdate.isPending}
        />
        {photoUpdate.isError && (
          <p className="text-red-600 dark:text-red-400 text-xs">{getErrorMessage(photoUpdate.error)}</p>
        )}
      </EditorBlock>

      <EditorBlock
        title="Secciones que gestiona"
        editable
        actions={
          <IconAction
            label="Guardar secciones"
            disabled={!sectionDirty || sectionsUpdate.isPending}
            onClick={() =>
              sectionsUpdate.mutate({ profileId: data.profile_id, sectionIds: selectedSectionIds })
            }
          >
            <Save size={13} aria-hidden="true" />
          </IconAction>
        }
      >
        <p className="text-sm text-text-secondary">
          Pantallas del Admin bajo el dominio de este agente. Para quitar una sección de dominio por
          defecto, reasígnala a otro agente en Settings → Secciones.
        </p>
        <ThemedMultiSelect
          aria-label="Secciones de este agente"
          value={selectedSectionIds}
          onChange={setSelectedSectionIds}
          options={sectionOptions}
          placeholder="— Selecciona secciones —"
        />
        {sectionsUpdate.isError && (
          <p className="text-red-600 dark:text-red-400 text-xs">{getErrorMessage(sectionsUpdate.error)}</p>
        )}
      </EditorBlock>

      <EditorBlock
        title="Herramientas"
        editable
        actions={
          <>
            <IconAction
              label="Guardar herramientas"
              disabled={!toolsDirty || toolsUpdate.isPending}
              onClick={() =>
                toolsUpdate.mutate({ profileId: data.profile_id, toolNames: selectedToolNames })
              }
            >
              <Save size={13} aria-hidden="true" />
            </IconAction>
            <IconAction
              label="Restablecer al código"
              muted
              disabled={data.override_tools === null || toolsUpdate.isPending}
              onClick={() => toolsUpdate.mutate({ profileId: data.profile_id, toolNames: null })}
            >
              <RotateCcw size={13} aria-hidden="true" />
            </IconAction>
          </>
        }
      >
        <p className="text-sm text-text-secondary">
          Tools que este agente puede invocar. <code>delegate_to_specialist</code> se gestiona por
          nivel y no aparece aquí. Guardar reemplaza el set por defecto; Restablecer vuelve al código.
        </p>
        <ThemedMultiSelect
          aria-label="Herramientas de este agente"
          value={selectedToolNames}
          onChange={setSelectedToolNames}
          options={toolOptions}
          placeholder="— Selecciona herramientas —"
        />
        {toolsUpdate.isError && (
          <p className="text-red-600 dark:text-red-400 text-xs">{getErrorMessage(toolsUpdate.error)}</p>
        )}
      </EditorBlock>

      {data.can_delegate && (
        <EditorBlock
          title="Puede delegar a"
          editable
          actions={
            <>
              <IconAction
                label="Guardar delegación"
                disabled={!delegationDirty || delegationUpdate.isPending}
                onClick={() =>
                  delegationUpdate.mutate({
                    profileId: data.profile_id,
                    targetIds: selectedDelegateIds,
                  })
                }
              >
                <Save size={13} aria-hidden="true" />
              </IconAction>
              <IconAction
                label="Restablecer al código"
                muted
                disabled={data.delegation_is_default || delegationUpdate.isPending}
                onClick={() => {
                  delegationUpdate.mutate({ profileId: data.profile_id, targetIds: null })
                  setSelectedDelegateIds(data.default_delegation_target_ids)
                }}
              >
                <RotateCcw size={13} aria-hidden="true" />
              </IconAction>
            </>
          }
        >
          <p className="text-sm text-text-secondary">
            Solo especialistas de nivel inferior. Vacío = no delega a nadie. Restablecer vuelve a la
            lista completa permitida por el nivel.
          </p>
          <ThemedMultiSelect
            aria-label="Agentes destino de delegación"
            value={selectedDelegateIds}
            onChange={setSelectedDelegateIds}
            options={delegateOptions}
            placeholder="— Selecciona destinos —"
          />
          {delegationUpdate.isError && (
            <p className="text-red-600 dark:text-red-400 text-xs">
              {getErrorMessage(delegationUpdate.error)}
            </p>
          )}
        </EditorBlock>
      )}

      <EditorBlock
        title="Prompt de sistema"
        editable
        actions={
          <>
            <IconAction
              label="Guardar prompt"
              disabled={!promptDirty || promptUpdate.isPending}
              onClick={() =>
                promptUpdate.mutate({ profileId: data.profile_id, systemPromptSuffix: promptDraft })
              }
            >
              <Save size={13} aria-hidden="true" />
            </IconAction>
            <IconAction
              label="Restablecer al código"
              muted
              disabled={data.prompt_is_default || promptUpdate.isPending}
              onClick={() => {
                promptUpdate.mutate({ profileId: data.profile_id, systemPromptSuffix: null })
                setPromptDraft(data.default_suffix)
              }}
            >
              <RotateCcw size={13} aria-hidden="true" />
            </IconAction>
          </>
        }
      >
        <details className="text-xs text-text-muted">
          <summary className="cursor-pointer hover:text-text-secondary">Ver predeterminado en código</summary>
          <pre className="mt-2 p-3 rounded-xl bg-glass whitespace-pre-wrap font-mono text-[11px]">
            {data.default_suffix}
          </pre>
        </details>
        <textarea
          value={promptDraft}
          onChange={(e) => setPromptDraft(e.target.value)}
          rows={12}
          className="input-field text-sm font-mono leading-relaxed resize-y"
          aria-label="Prompt del especialista"
        />
        {promptUpdate.isError && (
          <p className="text-red-600 dark:text-red-400 text-xs">{getErrorMessage(promptUpdate.error)}</p>
        )}
      </EditorBlock>

      <EditorBlock
        title="Metodologías asignadas"
        editable
        actions={
          <IconAction
            label="Guardar metodologías"
            disabled={!methodologyDirty || methodologiesUpdate.isPending || methodologyOptions.length === 0}
            onClick={() =>
              methodologiesUpdate.mutate({
                profileId: data.profile_id,
                methodologyIds: selectedMethodologyIds,
              })
            }
          >
            <Save size={13} aria-hidden="true" />
          </IconAction>
        }
      >
        <p className="text-sm text-text-secondary">
          El agente consulta solo las que le asignes aquí (o las compartidas). Una metodología nueva
          asignada se asume en el siguiente turno.
        </p>
        {methodologyOptions.length === 0 ? (
          <p className="text-sm text-text-secondary">
            No hay metodologías todavía.{' '}
            <Link to="/career/operational-methodologies" className="text-primary hover:underline">
              Crear en Metodologías Operativas
            </Link>
          </p>
        ) : (
          <ThemedMultiSelect
            aria-label="Metodologías de este agente"
            value={selectedMethodologyIds}
            onChange={setSelectedMethodologyIds}
            options={methodologyOptions}
            placeholder="— Selecciona metodologías —"
          />
        )}
        {methodologiesUpdate.isError && (
          <p className="text-red-600 dark:text-red-400 text-xs">
            {getErrorMessage(methodologiesUpdate.error)}
          </p>
        )}
      </EditorBlock>

      <MemoryEditor
        agent={data}
        conversationCount={memory?.conversation_count ?? data.conversation_count}
        conversations={conversations}
        notes={memory?.notes ?? []}
        noteDraft={noteDraft}
        onNoteDraftChange={setNoteDraft}
        onAddNote={() => {
          if (!noteDraft.trim()) return
          notes.add.mutate(noteDraft.trim(), { onSuccess: () => setNoteDraft('') })
        }}
        onDeleteNote={(id) => notes.remove.mutate(id)}
        adding={notes.add.isPending}
        addError={notes.add.error}
      />

      <div className="flex items-center gap-2 pt-2">
        <button type="button" onClick={onCancel} className="btn-secondary">
          Cancelar
        </button>
      </div>
    </div>
  )
}

const MemoryEditor: React.FC<{
  agent: BedrockAgentCatalogItem
  conversationCount: number
  conversations: Array<{ session_id: string; title: string; updated_at: string }>
  notes: Array<{ id: string; text: string }>
  noteDraft: string
  onNoteDraftChange: (value: string) => void
  onAddNote: () => void
  onDeleteNote: (id: string) => void
  adding: boolean
  addError: unknown
}> = ({
  agent,
  conversationCount,
  conversations,
  notes,
  noteDraft,
  onNoteDraftChange,
  onAddNote,
  onDeleteNote,
  adding,
  addError,
}) => {
  if (!agent.has_own_memory) {
    return (
      <EditorBlock title="Memoria">
        <p className="text-sm text-text-secondary">
          Los agentes L3 no tienen chat ni memoria propia. El L1/L2 que los invoca resume el
          resultado de la tarea.
        </p>
      </EditorBlock>
    )
  }

  return (
    <EditorBlock
      title="Memoria propia"
      editable
      actions={
        <IconAction label="Guardar nota" disabled={!noteDraft.trim() || adding} onClick={onAddNote}>
          <Save size={13} aria-hidden="true" />
        </IconAction>
      }
    >
      <p className="text-sm text-text-secondary">
        Conversaciones de este perfil (corto plazo) y notas que Carlos le deja (se inyectan en el
        prompt de cada turno).
      </p>
      <p className="text-sm text-text">
        {conversationCount} conversación{conversationCount === 1 ? '' : 'es'}
      </p>
      {conversations.length > 0 && (
        <ul className="space-y-1 text-sm">
          {conversations.slice(0, 8).map((conv) => (
            <li key={conv.session_id} className="text-text-secondary">
              {conv.title}
            </li>
          ))}
        </ul>
      )}
      <div className="space-y-2">
        {notes.map((note) => (
          <div key={note.id} className="flex items-start gap-2 p-3 rounded-xl bg-glass">
            <p className="text-sm text-text flex-1 whitespace-pre-wrap">{note.text}</p>
            <button
              type="button"
              className="text-text-muted hover:text-red-500"
              aria-label="Eliminar nota"
              onClick={() => onDeleteNote(note.id)}
            >
              <Trash2 size={15} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
      <textarea
        value={noteDraft}
        onChange={(e) => onNoteDraftChange(e.target.value)}
        rows={3}
        className="input-field text-sm"
        placeholder="Nota para este agente (ej. preferencias de tono, excepciones)…"
        aria-label="Nueva nota de memoria"
      />
      {Boolean(addError) && (
        <p className="text-red-600 dark:text-red-400 text-xs">{getErrorMessage(addError)}</p>
      )}
    </EditorBlock>
  )
}

/** Alias: list and record share the same table-section chrome. */
export const AgentCatalogDetailPage = AgentCatalogPage
