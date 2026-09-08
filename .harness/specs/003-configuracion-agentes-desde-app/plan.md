---
titulo: Plan — Configuración de agentes desde la App (metodologías y herramientas)
tipo: plan
estado: verified
fecha: 2026-09-07
feature_id: "003"
spec: ./spec.md
---

> **Reapertura 2026-09-07 (Bloque F).** Se añade el frente 4 (consistencia del
> knowledge base). Los frentes 1–3 quedan como están (implementados y funcionales).

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
4. **Consistencia del knowledge base (reapertura 2026-09-07):** la verificación del
   punto 3 falló en vivo — el índice Qdrant `career_knowledge` está desincronizado por
   una migración de IDs nunca re-corrida. Se añade: módulo `knowledge_base.py`
   (`reindex_knowledge_base`), endpoint de operador, purga del gemelo heredado en el
   upsert, `RESOURCE_REGISTRY` con flag `vectorize`, reindex forzado en
   `set_agent_methodologies`, y `scripts/check_kb_consistency.py`.

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
| Metodologías | `cjhirashi-career-api/src/services/methodology_scope.py` | `set_agent_methodologies` fuerza reindex de las metodologías del usuario tras las escrituras PG (RF-014) |
| Servicio KB | `cjhirashi-career-api/src/services/bedrock/knowledge_base.py` (nuevo) | `reindex_knowledge_base(db, user_id=None)`: por usuario × `resource_key` vectorizable, re-embebe y upserta con IDs canónicos; luego purga huérfanos; devuelve conteos (RF-010/011/012) |
| Registro | `cjhirashi-career-api/src/routes/career_common.py` | `RESOURCE_VECTORIZE: Dict[str,bool]` poblado por `build_crud_router` y por los sitios que construyen `CareerRepository` a mano (RF-010, D-9) |
| Repositorio | `cjhirashi-career-api/src/repositories/career_repository.py` | `reindex_for_user(db, user_id) -> dict[str,int]` (loop por lotes, `_index_for_search` **awaited**, no fire-and-forget); `_index_for_search` deriva el `legacy_record_id` y lo pasa a `upsert_point` (RF-013) |
| Frontera Qdrant | `cjhirashi-career-api/src/services/qdrant_service.py` | `upsert_point(..., legacy_record_id=None)` borra el gemelo `_point_id(resource_key, legacy_record_id)` tras el upsert; `purge_orphans(valid_user_ids) -> int` (scroll + delete de payloads con `user_id` no vigente); `prune_stale_points(user_id, resource_key, keep_record_ids) -> int` (scroll filtrado por `user_id`+`resource_key`, delete de los `record_id` que ya no existen en PG) — necesario para que el reindex sea *rebuild* real (RF-010/011/013) |
| Rutas | `cjhirashi-career-api/src/routes/bedrock.py` | `POST /bedrock/knowledge-base/reindex` (`get_current_user`, síncrono) → conteos; `503` RFC 9457 si Qdrant cae a media corrida (RF-012) |
| Schemas | `cjhirashi-career-api/src/schemas/bedrock.py` | `BedrockKnowledgeBaseReindexResult` (`reindexed: dict[str,int]`, `purged_orphans: int`, `users: int`) |
| Script | `cjhirashi-career-api/scripts/check_kb_consistency.py` (nuevo) | compara conteo Qdrant vigente vs filas PG por `type` y usuario; solo imprime (D-10) |
| Frontend | `cjhirashi-career-admin/src/pages/AgentCatalogPage.tsx` | editor "Herramientas" (multiselect + "Restablecer al código") |
| Frontend | `cjhirashi-career-admin/src/pages/AgentToolsPage.tsx` | catálogo read-only alimentado desde `GET /tools/catalog` |
| Frontend | `cjhirashi-career-admin/src/api/bedrock.ts`, `hooks/useBedrockChat.ts`, `types/bedrock.ts` | clientes/hooks/tipos nuevos |

## 2 · Fronteras de salida

- **Postgres compartida** — nueva tabla `bedrock_agent_profile_tools` vía Alembic. Sin
  tocar tablas existentes.
- **AWS Bedrock** (`bedrock-runtime`, tool-calling) — sin cambio de contrato de tools; el
  set por perfil cambia por el override. Sin llamadas reales en tests (Art. 5, mockeado).
- **Qdrant** (`career_knowledge`) — **sí cambia** (reapertura): nuevas operaciones
  `purge_orphans` y borrado del gemelo en `upsert_point`; el reindexado masivo re-embebe
  (1 llamada Titan Embeddings por fila — coste, Art. 5: en tests todo mockeado). Sin
  cambio de esquema de la colección ni del modelo de embeddings.
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
| KB reindex (unit, Qdrant+embed mockeados) | `tests/unit/bedrock/test_knowledge_base_reindex.py` (nuevo) | RF-010: 1 upsert por fila vigente × usuario × recurso vectorizable, IDs canónicos · RF-011: purga de payloads con `user_id` no vigente · RF-012: shape del dict de conteos · RNF-003: 2ª corrida → `purged_orphans: 0`, mismos upserts · RNF-004: paginado por lotes (no un solo `select` de toda la tabla) |
| Purga gemelo (unit) | `tests/unit/bedrock/test_qdrant_orphan_purge.py` (nuevo) | RF-013: `_index_for_search` de `opm-33` → `upsert_point` recibe `legacy_record_id="33"` y borra `_point_id("operational-methodologies","33")` · record sin prefijo → sin `legacy_record_id` |
| Metodologías reindex forzado (unit) | `tests/unit/test_methodology_scope.py` (ampliar) | RF-014: `set_agent_methodologies` llama al reindex de las metodologías del usuario aunque `next_agent_profile_ids` devuelva `None` para todas |
| Registro `vectorize` (unit) | `tests/unit/test_resource_registry.py` (nuevo o ampliar) | RF-010/D-9: `RESOURCE_VECTORIZE` cubre todo `resource_key` de `RESOURCE_REGISTRY`; `cv-versions`/`pdf-*` → `False`, `operational-methodologies` → `True` |

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
`agent_profile_ids` en el payload. El camino de prompt (PG) está verificado en vivo y
funciona. El fallo real está en Qdrant → se ataca en RF-010..RF-015.

### RF-009 — catálogo de herramientas read-only
`profile_tools.list_builtin_tool_catalog()` devuelve `[{name, description}]` desde
`_RAW_TOOLS` (source of truth). `GET /tools/catalog` = `{ builtin: [...], mcp: [...] }`
(MCP desde `bedrock_service.list_custom_tools`). La descripción es la funcional completa;
enriquecer textos es opcional y no toca el `description` del tool-calling (D-5).

### RF-010 / RF-011 / RF-012 — reindexado del knowledge base
`services/bedrock/knowledge_base.py`:
- `async def reindex_knowledge_base(db, user_id: str | None = None) -> dict`:
  1. `user_ids = [user_id]` o `select(User.id)` si `None`. `valid = set(user_ids)` (para
     la purga se usa el conjunto **completo** de usuarios vigentes, no solo el alcance).
  2. Para cada `resource_key, model` de `RESOURCE_REGISTRY` con
     `RESOURCE_VECTORIZE.get(key, True)` → `repo = CareerRepository(model, resource_key=key)`;
     `n += await repo.reindex_for_user(db, uid)` (paginado por lotes de 100; cada fila
     `await self._index_for_search(row, uid)` **awaited**). Acumula por `resource_type`
     (`methodology` para `operational-methodologies`, si no `career_record`).
  3. `purged = await qdrant_service.purge_orphans(all_valid_user_ids)`.
  4. return `{"reindexed": {...}, "purged_orphans": purged, "users": len(user_ids)}`.
- `qdrant_service.purge_orphans(valid_user_ids)`: `scroll` toda la colección con
  `with_payload=["user_id"]`; junta los `point.id` cuyo `payload["user_id"]` (str) no
  esté en `valid_user_ids`; `delete` por lotes. Devuelve el conteo.
- **Ruta** `POST /bedrock/knowledge-base/reindex` (`bedrock.py`): `get_current_user`,
  llama `reindex_knowledge_base(db, None)`, responde `BedrockKnowledgeBaseReindexResult`.
  Si `qdrant_service` lanza a media corrida → `HTTPException(503, ...)` RFC 9457 con el
  detalle de hasta dónde llegó.
- **`RESOURCE_VECTORIZE`** en `career_common.py`: nuevo `register_resource(key, model,
  *, vectorize)` que puebla `RESOURCE_REGISTRY` **y** `RESOURCE_VECTORIZE`;
  `build_crud_router` y los sitios manuales (`pdf_templates.py` con `cv-versions` vía
  `build_crud_router(vectorize=False)`) lo llaman.
- **Directiva de Pausa (Fase 4, 2026-09-07):** el plan inicial asumía que
  "upsert de filas vivas + `purge_orphans`" bastaba para RF-010. La verificación en vivo
  mostró +2 puntos residuales para `usr-2` (filas borradas de PG sin propagar + 1 punto
  de `cv-versions`, hoy `vectorize=False`). Solución de raíz, sin cambiar el `RF-`:
  `prune_stale_points` por `(usuario, resource_key)` y poda a cero de los recursos
  `vectorize=False`. Con eso `check_kb_consistency.py` cierra en 0 divergencias / 0
  huérfanos (evidencia en `tasks.md` T-088).

### RF-013 — purga del gemelo heredado en el upsert
`CareerRepository._index_for_search`: tras calcular `record_id = obj.id`, si casa
`^[a-z]+-\d+$` → `legacy_record_id = obj.id.split("-", 1)[1]`, si no `None`. Se pasa a
`qdrant_service.upsert_point(..., legacy_record_id=legacy_record_id)`, que tras el
`client.upsert` canónico hace `client.delete` del punto
`_point_id(resource_key, legacy_record_id)` cuando no es `None` y difiere del canónico.

### RF-014 — `set_agent_methodologies` reindexa siempre
Al final de `set_agent_methodologies`, tras el bucle de `repo.update_for_user`, se
recorre **todas** las filas de `operational_methodologies` del usuario y se
`await repo._index_for_search(row, user_id)` (awaited, best-effort con log si Qdrant
cae). Esto auto-sana el índice en cada guardado del catálogo, aunque
`next_agent_profile_ids` devolviera `None`. Coste: 1 embedding por metodología del
usuario por guardado (aceptable para una acción de settings; RNF-004).

### RF-015 — cierre de RF-008 contra el índice real
Test e2e-ligero (unit con Qdrant en memoria/fake o mock de `search`): tras
`reindex_knowledge_base`, `qdrant_service.search(user_id, vector, resource_type="methodology")`
+ el filtro `applies_to_agent` devuelve las metodologías asignadas al perfil y ninguna
ajena. La verificación **en vivo** (JWT real + `search_knowledge_base`) va en el cierre
(Art. 3), con evidencia de terminal pegada.

### RF-016 / RF-017 / RF-018 — lectura selectiva de metodologías (Bloque J)

| Capa | Archivo | Cambio |
|---|---|---|
| Config | `src/config.py` | `BEDROCK_MAX_METHODOLOGY_RESULT_CHARS: int = 24000` |
| Tool `search` | `src/services/bedrock_service.py` (rama `search_knowledge_base`) | para `type=methodology`, mapear cada acierto a un **extracto** `{record_id, title, section, score, shared, excerpt (≤800 chars del `text`), read_full}` en vez del payload con `text` completo; añadir `instruction` ("lee completa solo la que aplicas, con get_career_record"). (RF-016/RNF-005) |
| Helper extracto | `src/services/bedrock_service.py` | `_methodology_snippet(row)` — parsea `title:`/`section:` de las primeras líneas de `_record_to_text` y recorta el resto |
| Truncado | `src/services/bedrock/tool_results.py` | `truncate_tool_result(result, limit: int | None = None)` — `limit` por llamada; default = `BEDROCK_MAX_TOOL_RESULT_CHARS` |
| Dispatch | `src/services/bedrock/tools.py` (`execute_tool`) | `_result_limit(name, tool_input)` → `BEDROCK_MAX_METHODOLOGY_RESULT_CHARS` si `name == "get_career_record"` y `resource_key == "operational-methodologies"`, si no el tope global; se pasa a `truncate_tool_result` (RF-017) |
| Prompt | `src/services/bedrock/prompt.py` (`methodology_assignment_block`) | la línea de `search_knowledge_base` explica: devuelve extractos → identifica la que necesitas → léela completa con `get_career_record` (resource_key `operational-methodologies`); **una por trabajo, no todas** (RF-018) |

Tests: `test_tool_results_truncation.py` (límite explícito respetado); nuevo
`test_methodology_snippets.py` (`search type=methodology` → extractos con `excerpt`
acotado, sin `text` completo; `execute_tool` de `get_career_record` sobre
`operational-methodologies` usa el tope de 24k); `test_prompt_methodology.py` (el bloque
nombra el patrón buscar→leer y "una por trabajo").

## § Impacto en documentación (Art. 11)

| Documento | Motivo | Tarea |
|---|---|---|
| `docs/sections/bedrock/README.md` | Nuevos endpoints `GET/PUT .../tools` y `GET /tools/catalog` | `[doc]` |
| `docs/BEDROCK-SYSTEM.md` | El catálogo gana override de herramientas por agente | `[doc]` |
| `docs/09-DECISIONS/026-configuracion-agentes-app.md` (nuevo ADR) | Decisión arquitectónica: override de tools por agente + catálogo read-only; agentes siguen en código (Opción A) | `[doc]` — redactar el ADR |
| `docs/09-DECISIONS/026-configuracion-agentes-app.md` (ampliar) | Reapertura 2026-09-07: causa raíz del índice Qdrant stale + decisión del reindexado idempotente (D-6..D-10) | `[doc]` — añadir sección "Reapertura" al ADR-026 |
| `docs/sections/bedrock/README.md` (ampliar) | Nuevo endpoint `POST /bedrock/knowledge-base/reindex` + nota de consistencia Qdrant↔PG | `[doc]` |
| `docs/BEDROCK-SYSTEM.md` (ampliar) | Sección "Knowledge base: reindexado y consistencia" (comando, endpoint, `check_kb_consistency.py`, paso post-deploy) | `[doc]` |
| `cjhirashi-career-api/scripts/` (README o cabecera) | Nuevo `check_kb_consistency.py` — cómo y cuándo correrlo | `[doc]` — docstring del script + mención en `docs/BEDROCK-SYSTEM.md` |
| `.harness/specs/003-configuracion-agentes-desde-app/contracts/knowledge-base.md` (nuevo) | Contrato request/response de `POST /bedrock/knowledge-base/reindex` | `[doc]` |
| `docs/BEDROCK-SYSTEM.md` §Knowledge base (ampliar) | Patrón buscar→leer para metodologías + `BEDROCK_MAX_METHODOLOGY_RESULT_CHARS` | `[doc]` T-D7 |
| `cjhirashi-career-api/src/services/bedrock/README.md` (§`truncate_tool_result`, §`search_knowledge_base`) | Nuevo parámetro `limit`; extractos para `type=methodology` | `[doc]` T-D7 |

