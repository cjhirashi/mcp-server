import React, { useState } from 'react'
import { Plug, Plus, Trash2 } from 'lucide-react'
import { useBedrockTools, useBedrockToolMutations, useBedrockToolsCatalog } from '@/hooks/useBedrockChat'
import { LoadingSpinner } from '@/components/LoadingSpinner'
import { getErrorMessage } from '@/utils/errors'

export const AgentToolsPage: React.FC = () => {
  const { data: tools, isLoading, isError, error } = useBedrockTools()
  const { data: toolsCatalog } = useBedrockToolsCatalog()
  const { createMutation, setEnabledMutation, deleteMutation } = useBedrockToolMutations()

  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    if (!name.trim() || !url.trim()) {
      setFormError('Nombre y URL son obligatorios.')
      return
    }
    createMutation.mutate(
      { name: name.trim(), url: url.trim() },
      {
        onSuccess: () => {
          setName('')
          setUrl('')
        },
        onError: (err) => setFormError(getErrorMessage(err)),
      }
    )
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-text">Herramientas del Agente</h1>
        <p className="text-text-secondary mt-2">
          Las herramientas integradas (CRUD y base de conocimiento) más los servidores MCP que registres aquí -
          quedan disponibles para el agente en el siguiente mensaje, sin necesidad de desplegar código.
        </p>
      </div>

      <div className="space-y-6">
        <div className="card">
          <div className="card-header">
            <h2 className="text-base font-semibold text-text">Herramientas integradas</h2>
            <p className="text-text-secondary text-xs mt-1">
              Parte del código de la aplicación - no se pueden editar ni eliminar desde aquí.
            </p>
          </div>
          <div className="card-body">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {(toolsCatalog?.builtin ?? []).map((tool) => (
                <div key={tool.name} className="p-3 rounded-xl bg-glass">
                  <p className="text-sm font-mono text-text">{tool.name}</p>
                  <p className="text-xs text-text-secondary mt-1">{tool.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h2 className="text-base font-semibold text-text flex items-center gap-2">
              <Plug size={17} className="text-primary" aria-hidden="true" />
              Servidores MCP
            </h2>
            <p className="text-text-secondary text-xs mt-1">
              Conecta un servidor MCP externo para darle nuevas herramientas al agente.
            </p>
          </div>
          <div className="card-body space-y-4">
            {isLoading && <LoadingSpinner fullScreen={false} message="Cargando herramientas..." />}
            {isError && <p className="text-red-600 dark:text-red-400 text-sm">{getErrorMessage(error)}</p>}

            {tools && tools.length === 0 && (
              <p className="text-text-secondary text-sm text-center py-4">
                Todavía no has registrado ningún servidor MCP.
              </p>
            )}

            {tools && tools.length > 0 && (
              <div className="space-y-2">
                {tools.map((tool) => (
                  <div key={tool.id} className="flex items-center justify-between gap-3 p-3 rounded-xl bg-glass">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-text truncate">{tool.name}</p>
                      <p className="text-xs text-text-secondary truncate">{tool.url}</p>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      <label className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer">
                        <input
                          type="checkbox"
                          checked={tool.is_enabled}
                          onChange={(e) => setEnabledMutation.mutate({ id: tool.id, isEnabled: e.target.checked })}
                        />
                        Activa
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`¿Eliminar el servidor MCP "${tool.name}"?`)) deleteMutation.mutate(tool.id)
                        }}
                        aria-label={`Eliminar ${tool.name}`}
                        title="Eliminar"
                        className="p-1.5 rounded-lg text-text-muted hover:bg-glass hover:text-red-500 transition-colors"
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <form onSubmit={handleCreate} className="pt-4 border-t border-border space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="mcp-name" className="form-label">
                    Nombre
                  </label>
                  <input
                    id="mcp-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="ej. exa-search"
                    className="input-field"
                  />
                </div>
                <div>
                  <label htmlFor="mcp-url" className="form-label">
                    URL del servidor MCP
                  </label>
                  <input
                    id="mcp-url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://..."
                    className="input-field"
                  />
                </div>
              </div>
              {formError && <p className="text-red-600 dark:text-red-400 text-xs">{formError}</p>}
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="btn-primary flex items-center gap-2 disabled:opacity-50"
              >
                <Plus size={15} aria-hidden="true" />
                Registrar servidor MCP
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
