---
titulo: Configuración de agentes desde la App (metodologías y herramientas)
tipo: spec
estado: verified
fecha: 2026-09-07
feature_id: "003"
covers:
  - cjhirashi-career-api/src/services/bedrock/agent_profiles.py
  - cjhirashi-career-api/src/services/bedrock/profile_catalog.py
  - cjhirashi-career-api/src/services/bedrock/agent_loop.py
  - cjhirashi-career-api/src/services/bedrock/tools.py
  - cjhirashi-career-api/src/services/bedrock/profile_tools.py
  - cjhirashi-career-api/src/services/bedrock/knowledge_base.py
  - cjhirashi-career-api/src/models/bedrock_agent_profile_tool.py
  - cjhirashi-career-api/alembic/versions/*_agent_profile_tools.py
  - cjhirashi-career-api/src/routes/bedrock.py
  - cjhirashi-career-api/src/routes/career_common.py
  - cjhirashi-career-api/src/schemas/bedrock.py
  - cjhirashi-career-api/src/services/methodology_scope.py
  - cjhirashi-career-api/src/services/qdrant_service.py
  - cjhirashi-career-api/src/services/bedrock_service.py
  - cjhirashi-career-api/src/services/bedrock/tool_results.py
  - cjhirashi-career-api/src/services/bedrock/tools.py
  - cjhirashi-career-api/src/services/bedrock/prompt.py
  - cjhirashi-career-api/src/config.py
  - cjhirashi-career-api/src/repositories/career_repository.py
  - cjhirashi-career-api/scripts/check_kb_consistency.py
  - cjhirashi-career-api/tests/unit/bedrock/test_profile_tools.py
  - cjhirashi-career-api/tests/unit/test_methodology_scope.py
  - cjhirashi-career-api/tests/unit/bedrock/test_knowledge_base_reindex.py
  - cjhirashi-career-api/tests/unit/bedrock/test_qdrant_orphan_purge.py
  - cjhirashi-career-api/tests/unit/bedrock/test_knowledge_base_routes.py
  - cjhirashi-career-api/tests/unit/test_resource_registry.py
  - cjhirashi-career-api/tests/unit/bedrock/test_tool_results_truncation.py
  - cjhirashi-career-api/tests/unit/bedrock/test_methodology_snippets.py
  - cjhirashi-career-api/tests/unit/bedrock/test_prompt_methodology.py
  - cjhirashi-career-api/src/services/README.md
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
  - .harness/specs/003-configuracion-agentes-desde-app/contracts/knowledge-base.md
anchor_commit: c855a19d
anchor_mode: strict
---

> **Reapertura (2026-09-07).** El Bloque F ("adopción de metodologías", RF-006/007/008)
> se cerró `verified` con tests puros/mockeados que nunca inspeccionaron el índice
> Qdrant real. En vivo el agente **sigue sin reconocer** metodologías (re)asignadas.
> Causa raíz: índice `career_knowledge` stale por una migración de IDs nunca
> re-indexada. Esta reapertura añade RF-010..RF-015 / RNF-003..RNF-004 y el Bloque I.
> El frente de **herramientas por agente** (RF-001..RF-005, RF-009) sí quedó funcional
> y no se toca.
>
> **2ª reapertura (2026-09-07, Bloque J).** Con el índice ya sano, el agente recibía la
> metodología pero **truncada** (`opm-61` = 15,6k chars > tope de tool-results 8k). El
> modelo de consumo correcto es "lee sólo la metodología que ocupa este trabajo, entera":
> `search` devuelve extractos (RF-016), la lectura de una va con presupuesto propio
> (RF-017), el prompt lo guía (RF-018).

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
- **Metodologías — causa raíz (hallada 2026-09-07, reapertura de 003):** el camino de
  prompt (catálogo desde PG, `list_assigned_methodologies` → `methodology_assignment_block`)
  **sí funciona** — medido en vivo devuelve las asignaciones correctas por perfil. El que
  falla es `search_knowledge_base type=methodology`, que lee de **Qdrant**. El índice
  `career_knowledge` quedó *stale* por una migración de IDs (usuario entero `2` → `"usr-2"`,
  record `33` → `"opm-33"`) que **nunca se re-corrió**: como `_point_id` deriva de
  `resource_key:record_id`, los upserts nuevos no pisan los viejos y la colección acumula
  dos generaciones. `qdrant_service.search` filtra por `user_id` exacto, así que solo ve
  la minoría re-escrita tras la migración. Medido en vivo: `usr-2` tiene **23** metodologías
  en PG y solo **7** puntos vigentes en Qdrant (16 huérfanos con `user_id=2`); además
  **231** puntos `career_record` huérfanos vs 107 vigentes (⇒ `search_knowledge_base` de
  registros de carrera **también** está degradado). `set_agent_methodologies` agrava:
  **salta el re-index** cuando `next_agent_profile_ids` devuelve `None` (reasignación sin
  cambio neto de compartición). El Bloque F cerró RF-007/RF-008 en falso.
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
- **Consistencia del knowledge base (reapertura Bloque F, 2026-09-07):** función
  idempotente `reindex_knowledge_base(db, user_id=None)` que reconstruye en Qdrant un
  punto por fila vigente de cada tabla vectorizable (metodologías + registros de carrera)
  de cada usuario y **purga los puntos huérfanos** de la migración de IDs; endpoint de
  operador `POST /bedrock/knowledge-base/reindex` (síncrono, todos los usuarios); purga
  del **gemelo heredado** en cada upsert; `set_agent_methodologies` **reindexa siempre**
  las metodologías cuyo estado evaluó; `RESOURCE_REGISTRY` pasa a registrar el flag
  `vectorize`; script operativo `scripts/check_kb_consistency.py`.
- **Lectura selectiva de metodologías (Bloque J, 2026-09-07):** `search_knowledge_base
  type=methodology` devuelve **extractos** (para ubicar cuál sirve), no el texto completo;
  la lectura entera de **una** metodología (`get_career_record` sobre
  `operational-methodologies`) usa un presupuesto propio `BEDROCK_MAX_METHODOLOGY_RESULT_CHARS`
  (24000) para que entre sin truncar; el prompt indica "una por trabajo, no todas".
- **Catálogo de herramientas (read-only):** listar todas las tools (integradas + MCP)
  con su descripción funcional completa; sin edición de la definición de cada tool.
- Trazabilidad `RF-`/test de los tres frentes.

### Fuera de alcance
- Crear/eliminar agentes (siguen en código, ADR-012).
- Editar la definición de cada tool (nombre/schema/descripción) — es código (`tools.py`).
- Servidores MCP globales (`bedrock_custom_tools`) — ya gestionados en `/agent/tools`.
- Cambiar el routing de agentes (`_ROUTE_TO_PROFILE`).
- Reprocesar tablas no vectorizadas (`vectorize=False`: `cv-versions`, `pdf-*`): el
  agente las lee de Postgres, no de Qdrant.
- Cambiar el modelo de embeddings o el esquema de la colección `career_knowledge`.
- Migrar `_point_id` a otro esquema — `record_id` sigue siendo la clave natural.

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

### 3.6 Consistencia del knowledge base (Qdrant ↔ Postgres)

- **Recursos vectorizables — fuente única:** `routes/career_common.py` pasa a registrar,
  junto al modelo, el flag `vectorize` por `resource_key` (los pocos `CareerRepository`
  construidos fuera de `build_crud_router` se registran igual). Prohibida una lista a
  mano de qué se indexa.
- **`reindex_knowledge_base(db, user_id: str | None = None) -> dict`** (nuevo módulo
  `services/bedrock/knowledge_base.py`): para cada usuario alcanzado (todos si
  `user_id is None`):
  - por cada `resource_key` con `vectorize=True`: re-embebe y upserta un punto por fila
    vigente con `user_id`/`record_id` canónicos, y **poda** (`prune_stale_points`) los
    puntos de ese `(usuario, resource_key)` cuyo `record_id` ya no existe en Postgres
    (filas borradas cuyo hook de borrado best-effort nunca llegó a Qdrant);
  - por cada `resource_key` con `vectorize=False`: **poda a cero** los puntos que hubiera
    (recurso que estuvo indexado antes de marcarse no-vectorizable, p.ej. `cv-versions`);
  - al final, elimina de la colección todo punto cuyo `user_id` de payload no sea un id
    de usuario vigente (`purge_orphans`).
  Devuelve `{ "reindexed": { "<resource_type>": n, ... }, "purged_orphans": k,
  "users": u }`. Procesa en serie, por lotes, sin cargar todas las filas a memoria. El
  resultado es un **rebuild verdadero**: exactamente un punto por fila vigente de recurso
  vectorizable, cero para el resto (RF-010).
- **Purga del gemelo en upsert:** `qdrant_service.upsert_point` (llamado por
  `CareerRepository._index_for_search`) borra, además del upsert canónico, el punto
  heredado `uuid5(NAMESPACE_URL, "career_knowledge:{resource_key}:{legacy_id}")` donde
  `legacy_id` es el `record_id` sin el prefijo canónico del recurso (`opm-33` → `33`),
  cuando el recurso tiene prefijo conocido.
- **Endpoint:** `POST /bedrock/knowledge-base/reindex` — `get_current_user`, síncrono,
  reindexa **todos** los usuarios, responde `200` con el dict de conteos. Errores en
  formato RFC 9457.
- **Script operativo:** `scripts/check_kb_consistency.py` — compara, por `type` de
  payload y por usuario, conteo de puntos Qdrant vigentes vs filas PG; imprime
  divergencias y huérfanos. **No modifica nada.** Se corre post-deploy.

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

### Reapertura Bloque F — consistencia del knowledge base (2026-09-07)

- **RF-010** — CUANDO se invoque `reindex_knowledge_base`, el sistema DEBE dejar en la
  colección `career_knowledge` exactamente un punto por cada fila vigente de cada
  `resource_key` con `vectorize=True` de cada usuario alcanzado (con su `user_id` y
  `record_id` canónicos), y cero puntos para los `resource_key` con `vectorize=False` —
  un *rebuild* verdadero, no solo un upsert aditivo.
- **RF-011** — CUANDO se invoque `reindex_knowledge_base`, el sistema DEBE eliminar de
  la colección todo punto cuyo `user_id` de payload no corresponda a un usuario vigente.
- **RF-012** — El sistema DEBE exponer `POST /bedrock/knowledge-base/reindex`, sólo para
  usuario autenticado, que ejecuta el reindexado de todos los usuarios de forma síncrona
  y responde con el conteo por tipo de recurso reindexado y de huérfanos purgados.
- **RF-013** — CUANDO `CareerRepository` indexe (upsert) un registro cuyo `record_id`
  lleva prefijo canónico, el sistema DEBE eliminar el punto heredado del mismo registro
  con el id sin prefijo, si existe.
- **RF-014** — CUANDO se guarde la asignación de metodologías de un agente
  (`set_agent_methodologies`), el sistema DEBE reindexar en Qdrant todas las metodologías
  del usuario cuyo estado de asignación se evaluó, aunque `agent_profile_ids` no cambie.
- **RF-015** — MIENTRAS existan filas de `operational_methodologies` para un usuario,
  tras `reindex_knowledge_base` el sistema DEBE poder devolver por
  `search_knowledge_base type=methodology` la metodología asignada al perfil consultante
  (cierre de RF-008 contra el índice real, no sólo el filtro en memoria).

### Lectura selectiva de metodologías (2026-09-07, Bloque J)

Contexto: el agente sólo necesita **la metodología que aplica a este trabajo**, no todas
las asignadas ni todas las existentes. `search_knowledge_base type=methodology` devolvía
el `text` completo de cada acierto; con metodologías grandes (opm-61 ≈ 15,6k chars) el
resultado excede `BEDROCK_MAX_TOOL_RESULT_CHARS` (8k) y cae al recorte ciego → el agente
recibe un preview mutilado ("vista truncada").

- **RF-016** — CUANDO un agente consulte `search_knowledge_base type=methodology`, el
  sistema DEBE devolver por cada resultado un **extracto** (`record_id`, título, sección,
  un fragmento inicial acotado y la instrucción de lectura completa) y NO el contenido
  completo de la metodología.
- **RF-017** — CUANDO un agente lea una metodología con `get_career_record` sobre
  `operational-methodologies`, el sistema DEBE aplicar el presupuesto
  `BEDROCK_MAX_METHODOLOGY_RESULT_CHARS` (≥ la metodología vigente más grande) en lugar
  del tope global, de modo que el contenido llegue sin truncar mientras quepa.
- **RF-018** — El bloque de metodologías del system prompt DEBE instruir al agente a
  ubicar con `search_knowledge_base` la metodología pertinente y leer con
  `get_career_record` únicamente la que va a aplicar en ese trabajo, no todas.

## 5 · Casos límite y manejo de errores

- Override con tool inexistente → 400, sin persistir (RF-004).
- Override `null` → vuelve al default de código (botón "Restablecer al código").
- L3 (sin delegar): `delegate_to_specialist` fuera aunque esté en el override (RF-005).
- Metodología reasignada con Qdrant caído → el write a PG no debe fallar (indexación
  best-effort, ya es el contrato de `CareerRepository`); el catálogo del prompt (desde
  PG) sigue correcto; `search_knowledge_base` degrada a lo indexado.
- Agente L1 (orquestador): puede recibir tools como cualquier nivel (D-4); la jerarquía
  se preserva porque `delegate_to_specialist` sigue gestionado por nivel (D-2).
- **Reindex — usuario sin filas en una tabla** → 0 puntos para ese `type`, sin error.
- **Reindex — Qdrant caído a media corrida** → el endpoint responde `503` RFC 9457 e
  informa qué `resource_key` alcanzó; no deja el índice a medias en silencio.
- **Reindex idempotente** → segunda corrida seguida: mismos upserts, `purged_orphans: 0`
  (RNF-003).
- **Punto huérfano con `user_id` entero heredado (`2`)** → se purga (no casa con ningún
  `usr-*` vigente).
- **Registro cuyo `record_id` no lleva prefijo conocido** → no hay gemelo que purgar;
  upsert normal (RF-013 no aplica).
- **`set_agent_methodologies` con Qdrant caído** → el write a PG igual persiste; el
  reindex forzado de RF-014 es best-effort (se loguea), coherente con `CareerRepository`.

## 6 · Registro de decisiones y descartes

| # | Decisión | Porqué | Descartado |
|---|---|---|---|
| D-1 | Override = reemplazo total (`tool_names` JSONB nullable), como el `system_prompt_suffix` | Coherencia con el modelo existente; "Restablecer al código" trivial; UX idéntica al prompt que el operador ya conoce | Delta `added`/`removed` (más complejo; semántica de drift ante tools nuevas en código) |
| D-2 | `delegate_to_specialist` fuera del override, gestionado por nivel | Invariante de seguridad ya existente en `tools_for_profile`; un override no debe romper la jerarquía L1/L2→L3 | Permitir editar la delegación vía override de tools |
| D-3 | Validar nombres contra `all_tool_names()` y rechazar desconocidos (400) | Evita typos silenciosos que el loop luego ignora | Ignorar nombres desconocidos al guardar |
| D-4 | El L1 orquestador puede recibir tools como cualquier otro nivel | Decisión del operador: poder asignar herramientas a todos los agentes por igual; la jerarquía se preserva con D-2 (`delegate_to_specialist` sigue por nivel) | Restringir L1 a solo `delegate_to_specialist` siempre |
| D-5 | El catálogo de herramientas es read-only y se alimenta de `tools.py` (`_RAW_TOOLS`) + `bedrock_custom_tools` | La definición de cada tool es código; el catálogo es referencia para decidir la asignación. La descripción puede enriquecerse para el catálogo sin tocar la que va al tool-calling | Mantener la lista hardcoded de tools en el frontend (`AgentToolsPage.tsx`) |
| D-6 | Reabrir 003 (no crear feature 004) para la consistencia del KB | El Bloque F de 003 ya era dueño de RF-006/007/008 y los cerró en falso; el arreglo es el trabajo que ese bloque debió hacer | Feature nueva 004 |
| D-7 | Reindexado = función idempotente + endpoint de operador | Re-ejecutable a mano si vuelve a driftar; deja superficie desde la App; Art. 10 (solución reusable, no parche único) | Migración Alembic data-only (no re-ejecutable); `scripts/*.py` suelto sin superficie App |
| D-8 | Purga de huérfanos: barrido por `user_id` no canónico en el comando **+** gemelo por id-sin-prefijo en cada upsert | El barrido limpia el pasivo de la migración; el gemelo evita que una reasignación deje un duplicado hasta el siguiente reindex completo | Solo barrido; migrar `_point_id` a otro esquema |
| D-9 | `RESOURCE_REGISTRY` registra el flag `vectorize` por recurso | Fuente única de qué se indexa; el propio comentario del registro prohíbe mantenerlo a mano | Lista hardcoded de resource_keys vectorizables dentro del comando |
| D-10 | Consistencia: unit de idempotencia/purga con dobles **+** `scripts/check_kb_consistency.py` operativo | El gate (`venv_test`) no garantiza Qdrant+PG en vivo; separar lógica (gate) de dato real (script post-deploy) | Test de integración con Qdrant desechable en el bloque `rest-http` del gate |
| D-11 | `search type=methodology` devuelve **extractos**; la lectura entera va por `get_career_record` con presupuesto propio (patrón buscar→leer) | El agente sólo aplica **una** metodología por trabajo; devolver todas enteras revienta el tope de tool-results (opm-61 15,6k > 8k) y encarece cada turno con texto que no va a usar | Subir el tope global `BEDROCK_MAX_TOOL_RESULT_CHARS` (afecta a todas las tools cada turno); chunkear metodologías por sección en Qdrant (cambio mayor, re-index por secciones) |
| D-12 | `BEDROCK_MAX_METHODOLOGY_RESULT_CHARS = 24000` | Cubre la metodología vigente más grande (opm-61, 15,6k) con margen; el coste se paga sólo al leer una, no cada turno | Sin tope (turnos caros si una crece mucho); 16k (sin margen para crecimiento) |

## 7 · Requisitos no funcionales

- **RNF-001** — No se cambia el contrato de ninguna tool existente (`tools.py`); solo se
  filtra qué tools recibe cada perfil.
- **RNF-002** — La resolución del set de tools se hace **una vez por turno** (ya ocurre
  en `agent_loop.py`); añadir el override no debe introducir N queries por turno.
- **RNF-003** — `reindex_knowledge_base` DEBE ser idempotente: dos ejecuciones
  consecutivas sin escrituras intermedias dejan el mismo conjunto de puntos en la
  colección.
- **RNF-004** — El reindexado hace 1 llamada de embedding por fila vectorizable y DEBE
  procesar usuarios y recursos en serie, por lotes, sin materializar todas las filas de
  una tabla en memoria a la vez.
- **RNF-005** — El extracto de cada resultado de `search_knowledge_base type=methodology`
  DEBE mantenerse pequeño (fragmento ≤ ~800 caracteres) para que un `top_k` normal quepa
  con holgura en el presupuesto de tool-results.

