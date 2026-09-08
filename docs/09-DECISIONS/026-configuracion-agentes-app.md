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

## Reapertura — 2026-09-07 (consistencia del knowledge base)

**Qué falló.** La "verificación" de metodologías (Bloque F de la spec 003) se cerró
`verified` con tests puros/mockeados que nunca inspeccionaron el índice Qdrant real. En
producción el agente **seguía sin reconocer** metodologías (re)asignadas.

**Causa raíz.** El camino de prompt (catálogo desde Postgres) funciona. El que falla es
`search_knowledge_base type=methodology`, que lee de Qdrant (`career_knowledge`). El
índice quedó *stale* por una migración de IDs (usuario entero `2` → `"usr-2"`, record
`33` → `"opm-33"`) que **nunca se re-corrió**: `_point_id` deriva de
`resource_key:record_id`, así que los upserts nuevos no pisan los viejos y la colección
acumuló dos generaciones de puntos. `qdrant_service.search` filtra por `user_id` exacto
→ el agente solo veía la minoría re-escrita tras la migración (medido: 7 de 23
metodologías; además 231 puntos `career_record` huérfanos).

**Decisión.**

- **D-6** — Se corrige dentro de la spec 003 (reapertura del Bloque F), no en una feature
  nueva: ese bloque ya era dueño de RF-006/007/008.
- **D-7** — El saneo es una **función idempotente re-ejecutable** + endpoint de operador
  `POST /bedrock/knowledge-base/reindex` (síncrono, todos los usuarios), no una migración
  Alembic de datos ni un script suelto. Reconstruye Qdrant desde Postgres (fuente de
  verdad) y devuelve conteos.
- **D-8** — Doble purga de huérfanos: barrido por `user_id` no vigente en el comando
  (`qdrant_service.purge_orphans`) **+** borrado del gemelo heredado (id sin prefijo) en
  cada `upsert_point`.
- **D-9** — `routes/career_common.py` registra el flag `vectorize` por recurso
  (`RESOURCE_VECTORIZE`), fuente única de "qué se indexa"; prohibida una lista a mano.
- **D-10** — `set_agent_methodologies` fuerza el reindex de todas las metodologías del
  usuario tras cada guardado (antes lo saltaba cuando `agent_profile_ids` no cambiaba de
  estado), de modo que la App auto-sana el índice.
- Verificación: unit de idempotencia/purga con dobles + `scripts/check_kb_consistency.py`
  (compara Qdrant vs Postgres, solo lee) como check de post-deploy.

**Consecuencias.**

- Nuevo endpoint `POST /bedrock/knowledge-base/reindex` → `{reindexed, purged_orphans,
  users}`; `503` RFC 9457 si Qdrant cae a media corrida (idempotente, reintentable).
- `qdrant_service` gana `purge_orphans(valid_user_ids)` y `upsert_point(...,
  legacy_record_id=)`; `CareerRepository` gana `reindex_for_user` (awaited, por lotes) y
  `_legacy_record_id`.
- **Paso de despliegue:** tras cualquier migración de ids/`user_id`, correr el reindex y
  `check_kb_consistency.py`.
