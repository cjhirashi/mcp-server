---
titulo: Configuración de agentes desde la App (metodologías y herramientas)
tipo: spec
estado: verified
fecha: 2026-09-06
feature_id: "003"
covers:
  - cjhirashi-career-api/src/services/bedrock/agent_profiles.py
  - cjhirashi-career-api/src/services/bedrock/profile_catalog.py
  - cjhirashi-career-api/src/services/bedrock/agent_loop.py
  - cjhirashi-career-api/src/services/bedrock/tools.py
  - cjhirashi-career-api/src/services/bedrock/profile_tools.py
  - cjhirashi-career-api/src/models/bedrock_agent_profile_tool.py
  - cjhirashi-career-api/alembic/versions/*_agent_profile_tools.py
  - cjhirashi-career-api/src/routes/bedrock.py
  - cjhirashi-career-api/src/schemas/bedrock.py
  - cjhirashi-career-api/src/services/methodology_scope.py
  - cjhirashi-career-api/src/repositories/career_repository.py
  - cjhirashi-career-api/tests/unit/bedrock/test_profile_tools.py
  - cjhirashi-career-api/tests/unit/test_methodology_scope.py
  - cjhirashi-career-admin/src/pages/AgentCatalogPage.tsx
  - cjhirashi-career-admin/src/api/bedrock.ts
  - cjhirashi-career-admin/src/hooks/useBedrockChat.ts
  - cjhirashi-career-admin/src/types/bedrock.ts
  - cjhirashi-career-admin/src/tests/pages/AgentCatalogPage.test.tsx
  - cjhirashi-career-admin/src/pages/AgentToolsPage.tsx
  - cjhirashi-career-api/tests/unit/bedrock/test_tools_catalog_routes.py
  - cjhirashi-career-api/tests/unit/bedrock/test_profile_tool_persistence.py
  - cjhirashi-career-api/tests/unit/test_methodology_indexing.py
  - cjhirashi-career-api/docs/sections/bedrock/README.md
  - docs/BEDROCK-SYSTEM.md
  - docs/09-DECISIONS/026-configuracion-agentes-app.md
  - .harness/specs/003-configuracion-agentes-desde-app/contracts/tools.md
anchor_commit: c855a19d
anchor_mode: advisory
---

# Configuración de agentes desde la App (metodologías y herramientas)

## 1 · Contexto del dominio

**Problema (una frase):** el "Catálogo de agentes" (`/settings/agents`) es la
superficie que el operador espera usar para configurar cada agente L1/L2/L3 (prompt,
memoria, metodologías, herramientas), pero dos de esas cuatro patas no funcionan como
se espera: (a) la reasignación de metodologías no se refleja en el agente, y (b) las
herramientas no son configurables en absoluto — viven solo en código.

**Estado actual (verificado en código):**
- Los agentes se definen en código (`services/bedrock/agent_profiles.py`): id, nivel,
  dominio, `system_prompt_suffix`, `allowed_tool_names`, etc. (ADR-012/013).
- Editable desde la App (overrides en PG): prompt (`bedrock_agent_profile_prompts`),
  memoria (notas), delegación, secciones, foto, y metodologías.
- **Metodologías:** la fuente de verdad es `operational_methodologies.agent_profile_ids`
  (JSONB; vacío/null = compartida). El endpoint
  `PUT /bedrock/agent-profiles/{id}/methodologies` (`methodology_scope.set_agent_methodologies`)
  y el multi-select del catálogo existen. `compose_system_prompt` inyecta el catálogo
  asignado cada turno (`methodology_assignment_block`) y `search_knowledge_base
  type=methodology` filtra por `applies_to_agent`. El `CareerRepository` indexa el payload
  en Qdrant con `agent_profile_ids`. En papel está completo; el operador reporta que el
  agente **no adopta** metodologías reasignadas o recién creadas.
- **Herramientas:** NO configurables por agente. `tools_for_profile()` calcula el set
  desde `allowed_tool_names` (código). El catálogo las muestra read-only (`tools`,
  `tools_count`). La página "Herramientas del Agente" solo gestiona servidores MCP
  globales (`bedrock_custom_tools`) y una lista parcial hardcoded de tools integradas,
  sin un catálogo completo con la descripción funcional de cada una.
- **Catálogo de herramientas (deseado):** el operador quiere una vista read-only,
  análoga al catálogo de agentes, que liste todas las tools (integradas + MCP) con la
  descripción completa de su funcionalidad, como referencia para decidir qué asignar a
  cada agente.

**Límites / dependencias:**
- Servicio dueño: `cjhirashi-career-api` (perfiles, tools, loop Bedrock, Alembic, Qdrant).
- Frontend: `cjhirashi-career-admin` (página Catálogo).
- Fronteras externas: AWS Bedrock (tool-calling), Qdrant (búsqueda de metodologías).

## 2 · Alcance

### En alcance
- **Herramientas por agente:** override persistido (default de código + añadir/quitar),
  endpoint, UI en el catálogo, y plomado al loop (`tools_for_profile` / `agent_loop.py`).
- **Metodologías:** garantizar que la reasignación desde el catálogo sea clara y que el
  agente **adopte** las metodologías asignadas (verificar y corregir el camino
  Qdrant + prompt si hace falta).
- **Catálogo de herramientas (read-only):** listar todas las tools (integradas + MCP)
  con su descripción funcional completa; sin edición de la definición de cada tool.
- Trazabilidad `RF-`/test de los tres frentes.

### Fuera de alcance
- Crear/eliminar agentes (siguen en código, ADR-012).
- Editar la definición de cada tool (nombre/schema/descripción) — es código (`tools.py`).
- Servidores MCP globales (`bedrock_custom_tools`) — ya gestionados en `/agent/tools`.
- Cambiar el routing de agentes (`_ROUTE_TO_PROFILE`).

## 3 · Modelo de datos y contratos de E/S

### 3.1 Herramientas — nueva tabla `bedrock_agent_profile_tools`
- Columnas: `profile_id` (PK, `agent_*`), `tool_names` (JSONB nullable), `updated_at`.
- Semántica: `NULL` = default de código (`tools_for_profile`). Valor presente =
  **reemplazo total** del set (análogo al `system_prompt_suffix` del prompt).
- Validación: cada nombre debe existir en `tools.all_tool_names()`; si no, 400.
- `delegate_to_specialist` **no es editable**: se gestiona por nivel (L3 sin delegar,
  L1/L2 con delegación) — igual que hoy en `tools_for_profile`.

### 3.2 Contrato de API
- `GET /bedrock/agent-profiles/{profile_id}/tools` →
  `{ default_tools: [...], effective_tools: [...], override_tools: [...] | null }`.
- `PUT /bedrock/agent-profiles/{profile_id}/tools` con `{ tool_names: [...] }` →
  guarda override; `{ tool_names: null }` restablece al default de código.

### 3.3 Resolución en runtime
- El set efectivo de tools = `override` (si presente) ∩ `all_tool_names()`, con la regla
  de `delegate_to_specialist` por nivel aplicada al final (D-2). `tools_for_profile`
  pasa a aceptar un override resuelto (o la resolución se hace en `agent_loop.py`).

### 3.4 Metodologías — invariante de adopción
- Al asignar/reasignar (`set_agent_methodologies`), el payload de Qdrant DEBE quedar con
  `agent_profile_ids` actualizado (re-index vía `CareerRepository` con `vectorize=True`).
- El catálogo inyectado en el prompt (`list_assigned_methodologies`) y el filtro de
  `search_knowledge_base` DEBEN devolver exactamente las metodologías asignadas al
  perfil (o las compartidas), nunca las ajenas.

### 3.5 Catálogo de herramientas (read-only)
- Fuente de verdad de las tools integradas: `services/bedrock/tools.py` (`_RAW_TOOLS`,
  con `name` + `description`). Las MCP: `bedrock_custom_tools`.
- `GET /bedrock/tools/catalog` → `{ builtin: [{name, description}], mcp: [{id, name,
  url, is_enabled}] }`. Solo lectura; no hay endpoint de escritura para la definición.
- La descripción es la funcional completa (puede enriquecerse para el catálogo sin
  tocar el `description` que va al tool-calling).

## 4 · Criterios de aceptación (EARS)

- **RF-001** — CUANDO el operador guarde un override de herramientas de un agente, el
  sistema DEBE persistirlo y el agente DEBE usar exactamente ese conjunto de tools en el
  siguiente turno.
- **RF-002** — SI un agente no tiene override de herramientas, el sistema DEBE usar el
  default de código (`tools_for_profile`).
- **RF-003** — El catálogo DEBE exponer el conjunto de tools (default, override y
  efectivo) de cada agente.
- **RF-004** — SI un override incluye un nombre de tool inexistente, el sistema DEBE
  rechazar con 400 y no persistir nada.
- **RF-005** — `delegate_to_specialist` DEBE seguir gestionado por nivel, ignorando el
  override.
- **RF-006** — CUANDO el operador reasigne metodologías de un agente desde el catálogo,
  el cambio DEBE persistir y aparecer en el catálogo del prompt en el siguiente turno.
- **RF-007** — CUANDO se cree o reasigne una metodología, el sistema DEBE (re)indexar
  Qdrant con el `agent_profile_ids` vigente.
- **RF-008** — CUANDO un agente consulte `search_knowledge_base type=methodology`, DEBE
  recibir solo las metodologías asignadas a su perfil (o las compartidas), nunca las
  ajenas.
- **RF-009** — El catálogo de herramientas DEBE listar todas las tools (integradas y
  MCP) con la descripción funcional completa de cada una, en modo solo-lectura.

## 5 · Casos límite y manejo de errores

- Override con tool inexistente → 400, sin persistir (RF-004).
- Override `null` → vuelve al default de código (botón "Restablecer al código").
- L3 (sin delegar): `delegate_to_specialist` fuera aunque esté en el override (RF-005).
- Metodología reasignada con Qdrant caído → el write a PG no debe fallar (indexación
  best-effort, ya es el contrato de `CareerRepository`); el catálogo del prompt (desde
  PG) sigue correcto; `search_knowledge_base` degrada a lo indexado.
- Agente L1 (orquestador): puede recibir tools como cualquier nivel (D-4); la jerarquía
  se preserva porque `delegate_to_specialist` sigue gestionado por nivel (D-2).

## 6 · Registro de decisiones y descartes

| # | Decisión | Porqué | Descartado |
|---|---|---|---|
| D-1 | Override = reemplazo total (`tool_names` JSONB nullable), como el `system_prompt_suffix` | Coherencia con el modelo existente; "Restablecer al código" trivial; UX idéntica al prompt que el operador ya conoce | Delta `added`/`removed` (más complejo; semántica de drift ante tools nuevas en código) |
| D-2 | `delegate_to_specialist` fuera del override, gestionado por nivel | Invariante de seguridad ya existente en `tools_for_profile`; un override no debe romper la jerarquía L1/L2→L3 | Permitir editar la delegación vía override de tools |
| D-3 | Validar nombres contra `all_tool_names()` y rechazar desconocidos (400) | Evita typos silenciosos que el loop luego ignora | Ignorar nombres desconocidos al guardar |
| D-4 | El L1 orquestador puede recibir tools como cualquier otro nivel | Decisión del operador: poder asignar herramientas a todos los agentes por igual; la jerarquía se preserva con D-2 (`delegate_to_specialist` sigue por nivel) | Restringir L1 a solo `delegate_to_specialist` siempre |
| D-5 | El catálogo de herramientas es read-only y se alimenta de `tools.py` (`_RAW_TOOLS`) + `bedrock_custom_tools` | La definición de cada tool es código; el catálogo es referencia para decidir la asignación. La descripción puede enriquecerse para el catálogo sin tocar la que va al tool-calling | Mantener la lista hardcoded de tools en el frontend (`AgentToolsPage.tsx`) |

## 7 · Requisitos no funcionales

- **RNF-001** — No se cambia el contrato de ninguna tool existente (`tools.py`); solo se
  filtra qué tools recibe cada perfil.
- **RNF-002** — La resolución del set de tools se hace **una vez por turno** (ya ocurre
  en `agent_loop.py`); añadir el override no debe introducir N queries por turno.

