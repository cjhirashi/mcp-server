---
titulo: Tasks — Configuración de agentes desde la App (metodologías y herramientas)
tipo: tasks
estado: verified
fecha: 2026-09-07
feature_id: "003"
spec: ./spec.md
plan: ./plan.md
---

> **Reapertura 2026-09-07.** Bloques A–H cerrados y funcionales (frentes 1–3). El
> Bloque F cerró RF-007/RF-008 en falso (tests mockeados, índice Qdrant nunca
> inspeccionado). Se añade el **Bloque I** (consistencia del knowledge base) que cubre
> RF-010..RF-015 / RNF-003..RNF-004 y cierra de verdad RF-008.

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

> **T-050/T-051 — insuficientes (reapertura).** Verde en verde no probó nada: los tests
> son puros/mockeados y el bug vive en el índice Qdrant real. RF-007/008 pasan a
> **Reabierto**; su cierre real está en el Bloque I (T-078/T-081/T-087).

## Bloque I — Consistencia del knowledge base (reapertura, RF-010..RF-015)

- [x] **T-070** `[test]` (cubre RF-010/RNF-004) — Nuevo
  `tests/unit/bedrock/test_knowledge_base_reindex.py`: `reindex_knowledge_base(db, None)`
  con `RESOURCE_REGISTRY` reducido y `embed_text`/`qdrant_service` mockeados → un
  `upsert_point` por fila viva × usuario × recurso vectorizable, con `user_id`/`record_id`
  canónicos; las filas se leen **paginadas** (≥2 llamadas de página para >100 filas), no
  en un `select` único. Rojo (módulo no existe).
- [x] **T-071** `[code]` (cubre RF-010) — `services/bedrock/knowledge_base.py`
  (`reindex_knowledge_base`), `CareerRepository.reindex_for_user` (loop por lotes de 100,
  `_index_for_search` **awaited**), `RESOURCE_VECTORIZE` en `routes/career_common.py`
  poblado por `build_crud_router` + sitios manuales. Verde T-070.
- [x] **T-072** `[test]` (cubre RF-011/RNF-003) — Mismo archivo:
  `qdrant_service.purge_orphans({"usr-1","usr-2"})` borra los puntos con
  `payload.user_id` fuera del set (incl. enteros heredados); 2ª corrida seguida →
  devuelve 0 y no reupserta. Rojo.
- [x] **T-073** `[code]` (cubre RF-011/RNF-003) — `qdrant_service.purge_orphans` (scroll
  + delete por lotes) y su llamada al final de `reindex_knowledge_base` con el set
  **completo** de usuarios vigentes. Verde T-072.
- [x] **T-074** `[test]` (cubre RF-012) — Ampliar
  `tests/unit/bedrock/test_tools_catalog_routes.py` (o nuevo
  `test_knowledge_base_routes.py`): `POST /bedrock/knowledge-base/reindex` con
  `reindex_knowledge_base` mockeado → `200` con `{reindexed, purged_orphans, users}`;
  si el mock lanza → `503` con cuerpo RFC 9457. Rojo.
- [x] **T-075** `[code]` (cubre RF-012) — `BedrockKnowledgeBaseReindexResult` en
  `schemas/bedrock.py` + ruta en `routes/bedrock.py` (`get_current_user`, síncrona,
  manejo `503`). Verde T-074.
- [x] **T-076** `[test]` (cubre RF-013) — Nuevo
  `tests/unit/bedrock/test_qdrant_orphan_purge.py`: `_index_for_search` de un `obj.id =
  "opm-33"` → `upsert_point` recibe `legacy_record_id="33"` y se hace `delete` del
  `_point_id("operational-methodologies","33")`; `obj.id="opm-33"` sin match de patrón
  (`"weirdid"`) → `legacy_record_id is None`, sin `delete`. Rojo.
- [x] **T-077** `[code]` (cubre RF-013) — Derivación `^[a-z]+-\d+$` en
  `_index_for_search` + parámetro `legacy_record_id` en `qdrant_service.upsert_point`
  (delete del gemelo tras el upsert canónico). Verde T-076.
- [x] **T-078** `[test]` (cubre RF-014) — Ampliar `tests/unit/test_methodology_scope.py`:
  `set_agent_methodologies` con todas las metodologías ya en su estado final
  (`next_agent_profile_ids` → `None` para todas) **igual** dispara un reindex de cada
  metodología del usuario (spy sobre `_index_for_search`). Rojo.
- [x] **T-079** `[code]` (cubre RF-014) — Reindex forzado (awaited, best-effort con log)
  al final de `set_agent_methodologies`. Verde T-078.
- [x] **T-080** `[test]` (cubre RF-010/D-9) — Nuevo `tests/unit/test_resource_registry.py`:
  todo `resource_key` de `RESOURCE_REGISTRY` está en `RESOURCE_VECTORIZE`;
  `operational-methodologies` → `True`; `cv-versions`, `pdf-output-templates`,
  `pdf-template-styles` → `False`. Rojo/verde según T-071.
- [x] **T-081** `[test]` (cubre RF-015/RF-008) — Mismo `test_knowledge_base_reindex.py`
  con un Qdrant en memoria (fake) o `search` real sobre payloads sembrados: tras
  `reindex_knowledge_base`, `search(user_id, v, resource_type="methodology")` + filtro
  `applies_to_agent` devuelve las metodologías del perfil consultante y **ninguna**
  ajena. Rojo (hoy el fake no tiene puntos canónicos).
- [x] **T-082** `[code]` (cubre RF-015) — no aplicó: T-081 verde. El fallo de RF-008/015
  era 100% índice stale, sin bug de lógica en `search`/`applies_to_agent`.
- [x] **T-083** `[test]` (cubre RF-010 — Directiva de Pausa) — `test_qdrant_orphan_purge.py`:
  `prune_stale_points(user_id, resource_key, keep)` borra los puntos de ese
  `(usuario, recurso)` cuyo `record_id` no está en `keep`; noop si la colección no existe.
  `test_knowledge_base_reindex.py`: el reindex poda a cero los `resource_key`
  `vectorize=False` (`cv-versions`, `pdf-*`).
- [x] **T-084** `[code]` (cubre RF-010 — Directiva de Pausa) — `qdrant_service.prune_stale_points`;
  `CareerRepository.reindex_for_user` la llama con los ids vivos; `reindex_knowledge_base`
  la llama con `keep=[]` para los recursos no vectorizables. Verde T-083.
- [x] **T-D4** `[doc]` (cubre doc: script) — `scripts/check_kb_consistency.py` con
  docstring de uso (compara Qdrant vigente vs PG por `type`/usuario; solo imprime).
- [x] **T-D5** `[doc]` (cubre doc: ADR-026 / READMEs) — sección "Reapertura 2026-09-07"
  en `docs/09-DECISIONS/026-configuracion-agentes-app.md` (causa raíz + D-6..D-10);
  `POST /bedrock/knowledge-base/reindex` en `docs/sections/bedrock/README.md`; sección
  "Knowledge base: reindexado y consistencia" en `docs/BEDROCK-SYSTEM.md` (comando,
  endpoint, script, paso post-deploy).
- [x] **T-D6** `[doc]` (cubre doc: contracts) — `contracts/knowledge-base.md` con
  request/response del endpoint. **Hecho en Fase 2.**
- [x] **T-088** `[ops]` (cierre RF-008/RF-010/RF-011/RF-015 en vivo, Art. 3) —
  `cjhirashi-career-api` reconstruida y redeployada (`docker compose build api && up -d api`,
  healthy). Evidencia de terminal pegada:

  **`check_kb_consistency.py` ANTES del reindex:**
  ```
  === Consistencia knowledge base (Qdrant vs Postgres) ===
    career_record  usr-1      PG=    5 Qdrant=    3  <-- DIVERGE
    career_record  usr-2      PG=  260 Qdrant=  107  <-- DIVERGE
    methodology    usr-1      PG=    1 Qdrant=    0  <-- DIVERGE
    methodology    usr-2      PG=   23 Qdrant=    7  <-- DIVERGE
    Huérfanos (user_id no vigente): 252
  ```

  **`POST /bedrock/knowledge-base/reindex` (JWT real de `usr-2`, HTTP 200, 68 s):**
  ```
  {"reindexed":{"career_record":265,"methodology":24},"purged_orphans":0,"users":2}
  ```

  **`check_kb_consistency.py` DESPUÉS (EXIT 0):**
  ```
  === Consistencia knowledge base (Qdrant vs Postgres) ===
    career_record  usr-1      PG=    5 Qdrant=    5
    career_record  usr-2      PG=  260 Qdrant=  260
    methodology    usr-1      PG=    1 Qdrant=    1
    methodology    usr-2      PG=   23 Qdrant=   23
    Huérfanos (user_id no vigente): 0
  OK: cuadran y sin huérfanos.
  ```

  **`search_knowledge_base type=methodology` en vivo (`bedrock_service._execute_tool`), por perfil:**
  ```
  === agent_professional_identity: 7 metodologías ===
     opm-47/53/33/46/44/29  aids=['agent_professional_identity']  ·  opm-37  aids=[] (compartida)
  === agent_pdf_design: 3 metodologías ===
     opm-59/57  aids=['agent_pdf_design','agent_pdf_render']  ·  opm-37  aids=[] (compartida)
  === agent_networking: 2 metodologías ===
     opm-55  aids=['agent_networking']  ·  opm-37  aids=[] (compartida)
  ```
  Cada perfil recibe solo lo asignado + lo compartido, nunca lo ajeno (RF-008), y ahora
  **sí lo recibe** (antes el índice devolvía casi nada) (RF-015).

## Bloque J — Lectura selectiva de metodologías (2ª reapertura, RF-016..RF-018)

- [x] **T-090** `[test]` (cubre RF-017) — Ampliar `test_tool_results_truncation.py`:
  `truncate_tool_result(result, limit=24000)` respeta el `limit` pasado (no el global);
  un `{"item":{"content": "X"*20000}}` cabe entero con `limit=24000` y se recorta con
  `limit=8000`. Rojo (la firma no acepta `limit`).
- [x] **T-091** `[code]` (cubre RF-017) — `truncate_tool_result(result, limit=None)` +
  `_cap_record_fields(result, limit)` ya lo acepta; `config.BEDROCK_MAX_METHODOLOGY_RESULT_CHARS
  = 24000`; `tools.execute_tool` calcula `_result_limit(name, tool_input)` y lo pasa.
  Verde T-090.
- [x] **T-092** `[test]` (cubre RF-016/RNF-005) — Nuevo `test_methodology_snippets.py`:
  `_execute_tool("search_knowledge_base", {"type":"methodology"})` con `qdrant_service.search`
  y `embed_text` mockeados devolviendo un acierto con `text` de 15k → el resultado es un
  extracto (`record_id`, `title`, `section`, `excerpt` ≤ 800, `read_full`), **sin** la
  clave `text` completa; incluye `instruction`. Rojo.
- [x] **T-093** `[code]` (cubre RF-016) — `_methodology_snippet(row)` +  rama
  `type=methodology` de `search_knowledge_base` mapea a extractos. Verde T-092.
- [x] **T-094** `[test]` (cubre RF-017 ruta dispatch) — Mismo `test_methodology_snippets.py`:
  `execute_tool("get_career_record", {"resource_key":"operational-methodologies","record_id":"opm-61"})`
  con repo mockeado (`content` 15k) → el resultado NO se trunca (cabe en 24k); el mismo
  sobre `resource_key="projects"` con 15k → sí se recorta (tope 8k). Rojo/verde.
- [x] **T-095** `[test]` (cubre RF-018) — Ampliar `test_prompt_methodology.py`:
  `methodology_assignment_block(profile, assigned)` para un perfil con
  `search_knowledge_base` contiene la guía "extractos" + "get_career_record" + "una por
  trabajo / no todas". Rojo.
- [x] **T-096** `[code]` (cubre RF-018) — ajustar la línea de `search_knowledge_base` en
  `methodology_assignment_block`. Verde T-095.
- [x] **T-D7** `[doc]` — `docs/BEDROCK-SYSTEM.md` §Knowledge base (patrón buscar→leer +
  `BEDROCK_MAX_METHODOLOGY_RESULT_CHARS`); `src/services/bedrock/README.md`
  (`truncate_tool_result` gana `limit`; `search type=methodology` devuelve extractos).
- [x] **T-097** `[ops]` (cierre RF-016/RF-017/RF-018/RNF-005 en vivo, Art. 3) —
  `cjhirashi-career-api` reconstruida + redeployada; reindex re-corrido (payload con
  `title`/`section`). Evidencia pegada:
  ```
  BEDROCK_MAX_TOOL_RESULT_CHARS       = 8000
  BEDROCK_MAX_METHODOLOGY_RESULT_CHARS = 24000

  --- search type=methodology (top_k=3, caller=agent_support) ---
  keys top-level: ['results', 'instruction']
    opm-37 | title='Mapa de Relaciones entre Tablas del Admi' | section='Metodología Operativa de la Bóveda' | excerpt_len=800 | text_key=False
    opm-56 | title='Proceso Único - Catálogo de Tags'         | section='Soporte'                            | excerpt_len=800 | text_key=False
    instruction: "Extractos, no el contenido completo. Identifica cuál aplica a ESTE trabajo y léela entera …"
  (opm-61 NO aparece: asignada solo a agent_methodologies — RF-008 sigue vigente)

  --- get_career_record opm-61 (caller=agent_support) ---
    item keys: [id, user_id, title, section, subsection, description, content, agent_profile_ids, notes, created_at, updated_at]
    content chars: 15611
    ¿marcador de truncado?: False   <-- llega ENTERA (tope 24000)
  ```

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
| RF-007 | T-050, T-051, T-078, T-079, T-088 | test_methodology_scope::test_set_agent_methodologies_forces_reindex_without_net_change · T-088 (vivo, evidencia pegada) | Pass |
| RF-008 | T-050, T-051, T-081, T-088 | test_knowledge_base_reindex::test_search_methodology_returns_assigned_only_after_reindex · T-088 (vivo: search por 3 perfiles, evidencia pegada) | Pass |
| RF-009 | T-020, T-021, T-060, T-061 | test_tools_catalog_routes::test_get_tools_catalog_lists_builtin_and_mcp · test_profile_tools::test_list_builtin_tool_catalog_has_name_and_description | Pass |
| RF-010 | T-070, T-071, T-080, T-083, T-084, T-088 | test_knowledge_base_reindex::test_reindex_upserts_one_point_per_row · ::test_reindex_prunes_non_vectorized_resources_to_empty · test_qdrant_orphan_purge::test_prune_stale_points_removes_rows_not_in_keep_set · test_resource_registry::test_vectorize_flag_covers_every_registered_resource · T-088 (check_kb_consistency EXIT 0) | Pass |
| RF-011 | T-072, T-073, T-088 | test_qdrant_orphan_purge::test_purge_orphans_deletes_only_non_current_users · ::test_purge_orphans_noop_when_collection_missing · T-088 (252→0 huérfanos) | Pass |
| RF-012 | T-074, T-075 | test_knowledge_base_routes::test_post_reindex_returns_counts · ::test_post_reindex_qdrant_down_returns_503 · ::test_post_reindex_requires_auth | Pass |
| RF-013 | T-076, T-077 | test_qdrant_orphan_purge::test_index_for_search_passes_legacy_id_and_deletes_twin · ::test_no_twin_delete_when_id_has_no_numeric_suffix · ::test_legacy_record_id_derivation | Pass |
| RF-014 | T-078, T-079 | test_methodology_scope::test_set_agent_methodologies_forces_reindex_without_net_change | Pass |
| RF-015 | T-081, T-088 | test_knowledge_base_reindex::test_search_methodology_returns_assigned_only_after_reindex · T-088 (vivo: 7/3/2 metodologías por perfil, antes ~0) | Pass |
| RNF-001 | (revisión) | sin llamadas reales a Bedrock en ningún test (todas mockeadas) | Pass |
| RNF-002 | T-030, T-031 | test_profile_tools::test_effective_* (resolución pura; el loop llama `get_tool_override` una vez por turno, fuera del bucle de rondas) | Pass |
| RNF-003 | T-072, T-073 | test_knowledge_base_reindex::test_reindex_is_idempotent | Pass |
| RNF-004 | T-070, T-071 | test_knowledge_base_reindex::test_reindex_for_user_pages_rows_in_batches | Pass |
| RF-016 | T-092, T-093, T-097 | test_methodology_snippets::test_search_methodology_returns_excerpts_not_full_text · ::test_search_career_record_still_returns_raw_rows · test_methodology_indexing (payload title/section) · T-097 (vivo) | Pass |
| RF-017 | T-090, T-091, T-094, T-097 | test_tool_results_truncation::test_explicit_limit_overrides_global_setting · ::test_limit_none_uses_global_setting · test_methodology_snippets::test_get_methodology_not_truncated_under_budget · ::test_methodology_budget_covers_largest_and_beats_global · T-097 (vivo: opm-61 15,6k sin truncar) | Pass |
| RF-018 | T-095, T-096 | test_prompt_methodology::test_block_guides_search_then_read_one_methodology · ::test_block_without_search_tool_unchanged_guidance | Pass |
| RNF-005 | T-092, T-093 | test_methodology_snippets::test_methodology_excerpt_is_capped · T-097 (vivo: excerpt_len=800) | Pass |
| doc: 026-ADR | T-D1 | `docs/09-DECISIONS/026-configuracion-agentes-app.md` | hecho |
| doc: READMEs | T-D2 | `docs/sections/bedrock/README.md` + `docs/BEDROCK-SYSTEM.md` | hecho |
| doc: contracts/tools.md | T-D3 | `contracts/tools.md` | hecho |
| doc: reapertura ADR-026 + READMEs | T-D5 | ADR-026 §Reapertura · `docs/sections/bedrock/README.md` · `docs/BEDROCK-SYSTEM.md` · `src/services/README.md` | hecho |
| doc: script check_kb_consistency | T-D4 | docstring de `scripts/check_kb_consistency.py` | hecho |
| doc: contracts/knowledge-base.md | T-D6 | `contracts/knowledge-base.md` | hecho |
| doc: buscar→leer metodologías | T-D7 | `docs/BEDROCK-SYSTEM.md` §Knowledge base · `src/services/bedrock/README.md` §truncate_tool_result | hecho |

