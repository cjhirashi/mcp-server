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

## 4. Variables de entorno

Ver `.env.example` — `BEDROCK_DEFAULT_MODEL_ID`, `BEDROCK_DAILY_BUDGET_USD`, `AWS_ACCESS_KEY_ID`, etc.

## 5. Documentación relacionada

- [ADR-008](09-DECISIONS/008-bedrock-harness-local.md)
- [ADR-012](09-DECISIONS/012-bedrock-three-level-agents.md)
- [cjhirashi-career-api/docs/BEDROCK-HARNESS.md](../cjhirashi-career-api/docs/BEDROCK-HARNESS.md) — IAM y catálogo de modelos
- [cjhirashi-career-api/docs/sections/bedrock/README.md](../cjhirashi-career-api/docs/sections/bedrock/README.md)
- [cjhirashi-career-admin/docs/BEDROCK-CHAT.md](../cjhirashi-career-admin/docs/BEDROCK-CHAT.md)
