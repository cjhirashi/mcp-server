# ADR-026: Configuración de agentes desde la App (metodologías y herramientas)

## Estado

Aceptado — 2026-09-06

## Contexto

El "Catálogo de agentes" (`/settings/agents`) es la superficie donde el operador espera
configurar cada agente L1/L2/L3 (definidos en código por ADR-012/013): prompt, memoria,
metodologías y herramientas. Prompt y memoria ya eran editables; las metodologías tenían
endpoint y UI pero el operador reportaba que el agente no las adoptaba; las herramientas
no eran configurables en absoluto (vivían solo en `agent_profiles.py` vía
`allowed_tool_names`).

## Decisión

- **Herramientas por agente:** nueva tabla `bedrock_agent_profile_tools` (`profile_id` PK,
  `tool_names` JSONB nullable). El override **reemplaza** el set por defecto del código
  (análogo al `system_prompt_suffix`); `null` = default de código. `delegate_to_specialist`
  no es editable: se aplica por nivel (L1/L2 delegan, L3 no), igual que hoy.
- **Catálogo de herramientas read-only:** `GET /bedrock/tools/catalog` lista todas las
  tools integradas (`tools.py` `_RAW_TOOLS`) + MCP (`bedrock_custom_tools`) con su
  descripción funcional. Sin edición de la definición.
- **Metodologías:** se **verifica** (no se rediseña) el camino existente
  (`operational_methodologies.agent_profile_ids` → prompt cada turno →
  `search_knowledge_base`). El payload de Qdrant ya lleva `agent_profile_ids`.
- **Los agentes siguen naciendo en código (Opción A):** esto configura a los existentes.
  "Crear agentes desde la App" queda como feature futura.
- **D-4:** el L1 orquestador puede recibir tools de tarea como cualquier otro nivel; la
  jerarquía se preserva porque `delegate_to_specialist` sigue gestionado por nivel.

## Consecuencias

- Nuevos endpoints: `GET/PUT /bedrock/agent-profiles/{id}/tools`,
  `GET /bedrock/tools/catalog`.
- `tools_for_profile` se mantiene puro (default); el override se resuelve en
  `services/bedrock/profile_tools.py` y se ploma en `agent_loop.py` una vez por turno.
- El catálogo de agentes expone `default_tools` / `override_tools` / `effective_tools`.
- La página "Herramientas del Agente" deja la lista hardcoded y se alimenta del catálogo.
