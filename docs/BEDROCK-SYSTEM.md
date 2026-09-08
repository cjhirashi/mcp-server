# Sistema Bedrock — Guía maestra

Documento índice del Harness Converse (ADR-008, ADR-012).

## 1. Resumen

- **Harness** en `cjhirashi-career-api/src/services/bedrock/` — loop Converse, historial PG, tools, presupuesto, jerarquía de 3 niveles.
- **AWS:** solo `bedrock-runtime` (Converse + Titan Embeddings + Stable Image Core). Titan
  Image Generator (v1/v2) llegó a fin de vida y Nova Canvas quedó sin acceso habilitado
  para esta cuenta; la generación de imágenes usa `stability.stable-image-core-v1:1` en
  `us-west-2` (`BEDROCK_IMAGE_REGION`), región distinta a `BEDROCK_REGION` (Converse/
  embeddings en `us-east-1`).

## 2. Tres niveles y dos superficies de chat

| Nivel | Agente | Superficie | ¿Usuario? | Delegación |
|-------|--------|------------|-----------|------------|
| 1 | Orquestador | `/agent/chat` (general) | Sí | → L2 y L3 |
| 2 | Especialista de área | Sidebar contextual | Sí | → L3 |
| 3 | Especialista de tarea | Ninguna | No | — |

L1 no hace CRUD. L3 no tiene `POST /bedrock/chat` como agente principal.

El L2 que atiende el sidebar contextual de cada sección se asigna en **Settings →
Secciones del Admin** (ADR-024); sin agente asignado, esa sección no tiene chat
contextual y el turno degrada al orquestador.

## 3. Perfiles

**L2:** `agent_professional_identity`, `agent_search_operations`, `agent_digital_presence`, `agent_networking`, `agent_support`, `agent_methodologies`, `agent_pdf_design`

**L3:** `agent_pdf_render`, `agent_visual_design`, `agent_changelog`, `agent_task_manager`, `agent_linkedin_publishing`, `agent_vacancy_search`, `agent_cv_writing`, `agent_cover_letter_writing`

Definidos en `cjhirashi-career-api/src/services/bedrock/agent_profiles.py`.

**Configuración desde la App:** prompt, memoria, metodologías, delegación, secciones, foto
y — desde ADR-026 — **herramientas** son editables en el Catálogo de Agentes
(`/settings/agents`) como overrides en Postgres. Las herramientas usan
`bedrock_agent_profile_tools` (override que reemplaza el set de código); el catálogo
read-only de tools está en `GET /bedrock/tools/catalog`.

## 4. Knowledge base: reindexado y consistencia

El agente busca metodologías y registros de carrera por semántica en Qdrant
(colección `career_knowledge`), un índice **derivado de Postgres**: `CareerRepository`
re-indexa cada fila en cada escritura (best-effort). Una migración de ids o de `user_id`
que no re-indexe deja el índice *stale* — `search` filtra `user_id` exacto y el agente
"no encuentra" lo que sí existe en Postgres (ADR-026, reapertura 2026-09-07).

- **`POST /bedrock/knowledge-base/reindex`** (operador, síncrono): reconstruye el índice
  de todos los usuarios desde Postgres y purga los puntos huérfanos (payload `user_id`
  inexistente). Idempotente. Respuesta `{reindexed: {methodology, career_record},
  purged_orphans, users}`; `503` si Qdrant cae a media corrida (reintentable).
- **`scripts/check_kb_consistency.py`**: compara conteo Qdrant vigente vs filas Postgres
  por tipo y usuario, y cuenta huérfanos. Solo lee. Sale `1` si hay divergencias.
- **Paso de despliegue:** tras cualquier migración que toque ids o `user_id`, correr el
  reindex y luego `check_kb_consistency.py`.
- `RESOURCE_VECTORIZE` (en `routes/career_common.py`) es la fuente única de qué recursos
  se indexan; `set_agent_methodologies` fuerza el reindex de las metodologías del usuario
  en cada guardado del catálogo.

**Lectura selectiva de metodologías (patrón buscar→leer, ADR-026 §Reapertura).** El
agente sólo aplica **una** metodología por trabajo. `search_knowledge_base type=methodology`
devuelve **extractos** (`record_id`, título, sección, `excerpt` ≤ 800 chars, `read_full`),
no el procedimiento completo — sirve para *elegir* cuál. La metodología elegida se lee
entera con `get_career_record resource_key=operational-methodologies record_id=...`, que
recibe el presupuesto propio `BEDROCK_MAX_METHODOLOGY_RESULT_CHARS` (24000, vs. el tope
global `BEDROCK_MAX_TOOL_RESULT_CHARS` = 8000) para que una metodología grande (opm-61 ≈
15,6k) entre sin truncar. El coste sólo se paga al leer una, no cada turno. El bloque de
metodologías del system prompt guía este flujo ("una por trabajo, no todas").

## 5. Variables de entorno

Ver `.env.example` — `BEDROCK_DEFAULT_MODEL_ID`, `BEDROCK_DAILY_BUDGET_USD`, `AWS_ACCESS_KEY_ID`, etc.

## 6. Documentación relacionada

- [ADR-008](09-DECISIONS/008-bedrock-harness-local.md)
- [ADR-012](09-DECISIONS/012-bedrock-three-level-agents.md)
- [ADR-026](09-DECISIONS/026-configuracion-agentes-app.md) — configuración de agentes desde la App
- [cjhirashi-career-api/docs/BEDROCK-HARNESS.md](../cjhirashi-career-api/docs/BEDROCK-HARNESS.md) — IAM y catálogo de modelos
- [cjhirashi-career-api/docs/sections/bedrock/README.md](../cjhirashi-career-api/docs/sections/bedrock/README.md)
- [cjhirashi-career-admin/docs/BEDROCK-CHAT.md](../cjhirashi-career-admin/docs/BEDROCK-CHAT.md)
