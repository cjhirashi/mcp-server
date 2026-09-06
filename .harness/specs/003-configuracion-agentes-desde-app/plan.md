---
titulo: Plan — Configuración de agentes desde la App (metodologías y herramientas)
tipo: plan
estado: implemented
fecha: 2026-09-06
feature_id: "003"
spec: ./spec.md
---

# Plan de implementación (patrón por capas)

## 0 · Enfoque

Tres frentes, un solo dueño (`cjhirashi-career-api` para backend/loop + `admin` para UI):

1. **Herramientas por agente (nuevo):** override persistido en Postgres (default de código
   + reemplazo total), endpoint REST, editor en el catálogo y plomado async al loop Bedrock.
2. **Catálogo de herramientas read-only (nuevo):** `GET /tools/catalog` alimentado desde
   `tools.py` (`_RAW_TOOLS`) + `bedrock_custom_tools`, y su vista en el Admin.
3. **Metodologías (verificación):** el camino ya existe (`set_agent_methodologies` →
   `agent_profile_ids` → prompt cada turno → `search_knowledge_base`); el trabajo es
   **verificar** el invariante de adopción con tests y corregir solo si falla.

Capas tocadas: **modelo/migración → servicio (`profile_tools`) → rutas/schemas → loop →
catálogo → frontend admin → tests**. Sin cambio de contrato en las tools existentes
(`tools.py`); solo se filtra qué set recibe cada perfil (RNF-001).

Decisión de alcance (GATE 1): **Opción A** — los agentes siguen naciendo en código; esto
configura metodologías y herramientas de los que existen. "Crear agentes desde la App"
queda como feature futura (`004`).

## 1 · Fronteras y archivos por capa

| Capa | Archivo | Cambio |
|---|---|---|
| Modelo | `cjhirashi-career-api/src/models/bedrock_agent_profile_tool.py` (nuevo) | `BedrockAgentProfileTool`: `profile_id` PK `String(50)`, `tool_names` `JSONB` nullable, `updated_at` |
| Migración | `cjhirashi-career-api/alembic/versions/<rev>_agent_profile_tools.py` (nuevo) | `create_table` idempotente (`IF NOT EXISTS`), `down_revision` = head actual |
| Servicio | `cjhirashi-career-api/src/services/bedrock/profile_tools.py` (nuevo) | `default_tool_names(profile)`, `effective_tool_names(profile, override)`, `get_tool_state(db, profile)`, `set_tool_override(db, profile_id, tool_names)`, `list_builtin_tool_catalog()` |
| Servicio | `cjhirashi-career-api/src/services/bedrock/agent_profiles.py` | `tools_for_profile` se mantiene puro (default); el override se resuelve en `profile_tools` |
| Loop | `cjhirashi-career-api/src/services/bedrock/agent_loop.py` | cargar override **una vez por turno** y pasar el set efectivo a `converse_tool_specs` (RNF-002) |
| Rutas | `cjhirashi-career-api/src/routes/bedrock.py` | `GET/PUT /agent-profiles/{profile_id}/tools` + `GET /tools/catalog` |
| Schemas | `cjhirashi-career-api/src/schemas/bedrock.py` | `BedrockAgentToolsState`, `BedrockAgentToolsUpdateRequest`, `BedrockToolCatalogItem` |
| Catálogo | `cjhirashi-career-api/src/services/bedrock/profile_catalog.py` | serializar tools como `{ default_tools, override_tools, effective_tools }` |
| Metodologías | `cjhirashi-career-api/src/services/methodology_scope.py` | verificar re-index Qdrant; corregir solo si RF-007/008 fallan |
| Frontend | `cjhirashi-career-admin/src/pages/AgentCatalogPage.tsx` | editor "Herramientas" (multiselect + "Restablecer al código") |
| Frontend | `cjhirashi-career-admin/src/pages/AgentToolsPage.tsx` | catálogo read-only alimentado desde `GET /tools/catalog` |
| Frontend | `cjhirashi-career-admin/src/api/bedrock.ts`, `hooks/useBedrockChat.ts`, `types/bedrock.ts` | clientes/hooks/tipos nuevos |

## 2 · Fronteras de salida

- **Postgres compartida** — nueva tabla `bedrock_agent_profile_tools` vía Alembic. Sin
  tocar tablas existentes.
- **AWS Bedrock** (`bedrock-runtime`, tool-calling) — sin cambio de contrato de tools; el
  set por perfil cambia por el override. Sin llamadas reales en tests (Art. 5, mockeado).
- **Qdrant** — sin cambio; la verificación de metodologías confirma que el payload lleva
  `agent_profile_ids` y que `search_knowledge_base` filtra bien.
- **Sistema** — sin endpoint nuevo de infra.

## 3 · Contratos y gates de CI

- `cjhirashi-career-api/openapi.yaml` no existe committeado → sin gate Spectral/oasdiff;
  el bloque `rest-http` corre la suite pytest.
- Nuevo `contracts/tools.md` — request/response de `GET/PUT /agent-profiles/{id}/tools`
  y `GET /tools/catalog`, como referencia humana y base de los tests de ruta.
- Gate: `cd cjhirashi-career-api && venv_test/bin/python -m pytest -q` y
  `cd cjhirashi-career-admin && npx vitest run`.
- **Art. 5:** ninguna llamada real a Bedrock en los tests — todo mockeado.

## 4 · Estrategia de pruebas por capa

| Capa | Archivo de test | Cubre |
|---|---|---|
| Servicio `profile_tools` (unit, puro) | `tests/unit/bedrock/test_profile_tools.py` (nuevo) | RF-001/002/004/005: default, override reemplaza, tool desconocida → error, `delegate_to_specialist` por nivel |
| Loop (unit, override mockeado) | `tests/unit/bedrock/test_agent_loop_tools.py` (nuevo) | RF-001: el set efectivo (con override) llega a `converse_tool_specs`; RNF-002 (una sola resolución) |
| Rutas (unit, `TestClient` + db mockeada) | `tests/unit/bedrock/test_tools_catalog_routes.py` (nuevo) | RF-003/009: `GET /tools` y `GET /tools/catalog`; RF-004: PUT con tool inexistente → 400 |
| Metodologías (unit) | `tests/unit/test_methodology_scope.py` (ampliar) | RF-006/007/008: `set_agent_methodologies` persiste y re-indexa; `applies_to_agent` filtra correcto |
| Frontend catálogo (Vitest) | `cjhirashi-career-admin/src/tests/pages/AgentCatalogPage.test.tsx` (ampliar) | RF-003: el editor de herramientas muestra default/override/efectivo |

## 5 · Detalle por RF

### RF-001 / RF-002 — override de tools reemplaza al default
`profile_tools.py`:
- `default_tool_names(profile)` = `tools_for_profile(profile, all_tool_names())` (sin
  cambios de semántica).
- `effective_tool_names(profile, override)` = `set(override) & all_tool_names()` si
  `override is not None`, si no `default_tool_names(profile)`; después aplica la regla de
  `delegate_to_specialist` por nivel (D-2): `can_delegate` → añadir, si no → descartar.
- `set_tool_override(db, profile_id, tool_names)`: si `tool_names is None` → borrar fila
  (vuelve a default); si no → validar cada nombre contra `all_tool_names()` (RF-004) y
  upsert de la fila.

### RF-003 — el catálogo expone default/override/efectivo
`profile_catalog._serialize_definition` deja de emitir solo `tools`; emite
`default_tools`, `override_tools`, `effective_tools` (y conserva `tools` como alias del
efectivo para no romper `AgentToolsPage`/tests existentes).

### RF-004 — tool desconocida → 400
Validación en `set_tool_override` (y en el schema del PUT): `unknown = set(tool_names) -
all_tool_names()`; si no vacío, `HTTPException(400)` sin tocar DB.

### RF-005 — `delegate_to_specialist` por nivel
Se aplica en `effective_tool_names` SIEMPRE, tras el override (D-2). No es editable.

### RF-006 / RF-007 / RF-008 — adopción de metodologías
`methodology_scope.set_agent_methodologies` ya re-indexa vía `CareerRepository`
(`vectorize=True`) y el `CareerRepository._index_for_search` ya incluye
`agent_profile_ids` en el payload. El trabajo aquí es **verificar con tests** (ampliar
`test_methodology_scope.py`): reasignar una metodología → `list_assigned_methodologies`
la devuelve para el perfil asignado y no para otro; `applies_to_agent` filtra correcto.
Si un test queda rojo, se corrige la causa raíz (payload Qdrant / re-index), no el test.

### RF-009 — catálogo de herramientas read-only
`profile_tools.list_builtin_tool_catalog()` devuelve `[{name, description}]` desde
`_RAW_TOOLS` (source of truth). `GET /tools/catalog` = `{ builtin: [...], mcp: [...] }`
(MCP desde `bedrock_service.list_custom_tools`). La descripción es la funcional completa;
enriquecer textos es opcional y no toca el `description` del tool-calling (D-5).

## § Impacto en documentación (Art. 11)

| Documento | Motivo | Tarea |
|---|---|---|
| `docs/sections/bedrock/README.md` | Nuevos endpoints `GET/PUT .../tools` y `GET /tools/catalog` | `[doc]` |
| `docs/BEDROCK-SYSTEM.md` | El catálogo gana override de herramientas por agente | `[doc]` |
| `docs/09-DECISIONS/026-configuracion-agentes-app.md` (nuevo ADR) | Decisión arquitectónica: override de tools por agente + catálogo read-only; agentes siguen en código (Opción A) | `[doc]` — redactar el ADR |

