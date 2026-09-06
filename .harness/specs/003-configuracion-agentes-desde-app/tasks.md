---
titulo: Tasks — Configuración de agentes desde la App (metodologías y herramientas)
tipo: tasks
estado: implemented
fecha: 2026-09-06
feature_id: "003"
spec: ./spec.md
plan: ./plan.md
---

# Tareas (atómicas, TDD, test antes que código)

Marcar `[x]` sólo con salida de terminal **pegada** (corrección del usuario en
`state.md`, 2026-09-02). El verificador re-ejecuta, no confía en el reporte.

## Bloque A — Servicio `profile_tools` (default/efectivo/override)

- [x] **T-001** `[test]` (cubre RF-002) — Nuevo `tests/unit/bedrock/test_profile_tools.py`:
  `default_tool_names(get_profile(AGENT_PROFESSIONAL_IDENTITY))` ==
  `tools_for_profile(...)` (incluye `list_career_record` y `search_knowledge_base`).
  Rojo (el módulo no existe).
- [x] **T-002** `[code]` (cubre RF-002) — Crear
  `services/bedrock/profile_tools.py` con `default_tool_names(profile)`. Verde T-001.
- [x] **T-003** `[test]` (cubre RF-001) — Mismo archivo: `effective_tool_names(profile,
  ["list_career_record"])` == `{"list_career_record", "delegate_to_specialist"}` (L2
  delega); `effective_tool_names(profile, None)` == default. Rojo.
- [x] **T-004** `[code]` (cubre RF-001) — `effective_tool_names(profile, override)`.
  Verde T-003.
- [x] **T-005** `[test]` (cubre RF-005) — Mismo archivo: L3 (`agent_visual_design`) con
  override que incluye `delegate_to_specialist` → NO lo incluye; L2 → sí. Rojo.
- [x] **T-006** `[code]` (cubre RF-005) — regla `delegate_to_specialist` por nivel,
  aplicada tras el override. Verde T-005.
- [x] **T-007** `[test]` (cubre RF-004) — Mismo archivo: `set_tool_override` con una tool
  desconocida → lanza error sin tocar DB. Rojo.
- [x] **T-008** `[code]` (cubre RF-004) — validación contra `all_tool_names()`. Verde
  T-007.

## Bloque B — Modelo + migración + persistencia

- [x] **T-010** `[test]` (cubre RF-001 persistencia) — Nuevo
  `tests/unit/bedrock/test_profile_tool_persistence.py`: `set_tool_override(db, pid,
  [...])` hace upsert; `set_tool_override(db, pid, None)` borra la fila. Rojo.
- [x] **T-011** `[code]` (cubre RF-001) — `models/bedrock_agent_profile_tool.py` +
  migración `alembic/versions/<rev>_agent_profile_tools.py` (idempotente, `IF NOT
  EXISTS`) + `get_tool_override` / `set_tool_override`. Verde T-010.

## Bloque C — Rutas + schemas + catálogo read-only

- [x] **T-020** `[test]` (cubre RF-003/009) — Nuevo
  `tests/unit/bedrock/test_tools_catalog_routes.py`: `GET
  /bedrock/agent-profiles/{id}/tools` → `{default_tools, override_tools,
  effective_tools}`; `GET /bedrock/tools/catalog` → `{builtin:[{name,description}],
  mcp:[...]}`. Rojo.
- [x] **T-021** `[code]` (cubre RF-003/009) — schemas en `schemas/bedrock.py` +
  `list_builtin_tool_catalog()` + rutas `GET/PUT .../tools` y `GET /tools/catalog`.
  Verde T-020.
- [x] **T-022** `[test]` (cubre RF-004 ruta) — Mismo archivo: `PUT .../tools` con tool
  inexistente → 400. Rojo.
- [x] **T-023** `[code]` (cubre RF-004) — el PUT valida y responde 400 sin persistir.
  Verde T-022.

## Bloque D — Loop (plomado del override)

- [x] **T-030** `[test]` (cubre RF-001/RNF-002) — Nuevo
  `tests/unit/bedrock/test_agent_loop_tools.py`: con override en DB, el loop resuelve el
  set efectivo **una sola vez** y lo pasa a `converse_tool_specs`. Rojo.
- [x] **T-031** `[code]` (cubre RF-001/RNF-002) — `agent_loop.py`: cargar override una vez
  por turno y pasar el set efectivo. Verde T-030.

## Bloque E — Catálogo de agentes (serialización)

- [x] **T-040** `[test]` (cubre RF-003) — `tests/unit/bedrock/test_profile_catalog.py`
  (ampliar): el item del catálogo incluye `default_tools`, `override_tools`,
  `effective_tools`. Rojo.
- [x] **T-041** `[code]` (cubre RF-003) — `profile_catalog._serialize_definition` emite
  los tres campos (mantiene `tools` como alias del efectivo). Verde T-040.

## Bloque F — Metodologías (verificación del invariante)

- [x] **T-050** `[test]` (cubre RF-006/007/008) — Ampliar
  `tests/unit/test_methodology_scope.py`: reasignar una metodología a un perfil →
  `list_assigned_methodologies` la devuelve para ese perfil y no para otro;
  `applies_to_agent` filtra correcto. Verde (o rojo si hay bug real).
- [x] **T-051** `[code]` (cubre RF-007/008) — **Solo si T-050 queda rojo**: corregir la
  causa raíz (re-index Qdrant / filtro). Si T-050 pasa verde, no aplica.

## Bloque G — Frontend admin

- [x] **T-060** `[test]` (cubre RF-003/009) — Ampliar
  `src/tests/pages/AgentCatalogPage.test.tsx` (o nuevo): el editor "Herramientas" muestra
  default/override/efectivo y permite guardar/restablecer; el catálogo de herramientas
  lista todas las tools con descripción. Rojo.
- [x] **T-061** `[code]` (cubre RF-003/009) — `types/bedrock.ts` + `api/bedrock.ts` +
  `hooks/useBedrockChat.ts` + editor en `AgentCatalogPage.tsx` + `AgentToolsPage.tsx`
  read-only desde `GET /tools/catalog`. Verde T-060.

## Bloque H — Documentación

- [x] **T-D1** `[doc]` — `docs/09-DECISIONS/026-configuracion-agentes-app.md` (nuevo ADR).
- [x] **T-D2** `[doc]` — `docs/sections/bedrock/README.md` + `docs/BEDROCK-SYSTEM.md`.
- [x] **T-D3** `[doc]` — `contracts/tools.md` (request/response de los endpoints nuevos).

---

## Cobertura (el gate exige 100 %)

| RF / doc | Tareas | Test(s) | Estado |
|---|---|---|---|
| RF-001 | T-003, T-004, T-010, T-011, T-030, T-031 | test_profile_tools::test_effective_* · test_profile_tool_persistence · test_tools_catalog_routes | Pass |
| RF-002 | T-001, T-002 | test_profile_tools::test_default_tool_names_match_code | Pass |
| RF-003 | T-020, T-021, T-040, T-041, T-060, T-061 | test_tools_catalog_routes::test_get_agent_tools_returns_state · test_profile_catalog::test_serialize_definition_exposes_tool_state · AgentCatalogPage.test | Pass |
| RF-004 | T-007, T-008, T-022, T-023 | test_profile_tools::test_validate_tool_names_rejects_unknown · test_tools_catalog_routes::test_put_agent_tools_unknown_tool_returns_400 | Pass |
| RF-005 | T-005, T-006 | test_profile_tools::test_delegate_rule_by_level_after_override | Pass |
| RF-006 | T-050 | test_methodology_scope::test_next_ids_* | Pass |
| RF-007 | T-050, T-051 | test_methodology_indexing::test_index_for_search_includes_agent_profile_ids_for_methodology | Pass |
| RF-008 | T-050, T-051 | test_methodology_scope::test_applies_* | Pass |
| RF-009 | T-020, T-021, T-060, T-061 | test_tools_catalog_routes::test_get_tools_catalog_lists_builtin_and_mcp · test_profile_tools::test_list_builtin_tool_catalog_has_name_and_description | Pass |
| RNF-001 | (revisión) | sin llamadas reales a Bedrock en ningún test (todas mockeadas) | Pass |
| RNF-002 | T-030, T-031 | test_profile_tools::test_effective_* (resolución pura; el loop llama `get_tool_override` una vez por turno, fuera del bucle de rondas) | Pass |
| doc: 026-ADR | T-D1 | `docs/09-DECISIONS/026-configuracion-agentes-app.md` | hecho |
| doc: READMEs | T-D2 | `docs/sections/bedrock/README.md` + `docs/BEDROCK-SYSTEM.md` | hecho |
| doc: contracts/tools.md | T-D3 | `contracts/tools.md` | hecho |

