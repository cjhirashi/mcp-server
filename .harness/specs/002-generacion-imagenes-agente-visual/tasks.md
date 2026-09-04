---
titulo: Tasks — Pipeline de generación de imágenes del agente Visual
tipo: tasks
estado: draft
fecha: 2026-09-04
feature_id: "002"
spec: ./spec.md
plan: ./plan.md
---

# Tareas (atómicas, TDD, test antes que código)

Marcar `[x]` sólo con salida de terminal **pegada** (corrección del usuario en
`state.md`, 2026-09-02). El verificador re-ejecuta, no confía en el reporte.

Para RF-001/RF-002/RF-005/RF-007/RF-010 el código **ya existe** (corregido durante el
diagnóstico, Fase 0); su tarea `[test]` es retroactiva y debe pasar en **verde de
inmediato** — si no pasa, la corrección manual quedó incompleta y hay que arreglarla
antes de seguir, no ajustar el test.

## Bloque A — Cliente Bedrock (`image_client.py`)

- [x] **T-001** `[test]` (cubre RF-001, retroactivo) — Nuevo
  `tests/unit/bedrock/test_image_client.py`: mockear `boto3.client` (sin red);
  `generate_image_bytes(...)` invoca `invoke_model` con `modelId=settings.
  BEDROCK_IMAGE_MODEL_ID` y el cliente se crea con `region_name=settings.
  BEDROCK_IMAGE_REGION`; el `body` es `{"prompt", "aspect_ratio", "output_format":
  "png"}` (nunca `taskType`/`width`/`height`). Debe pasar en verde de inmediato.
- [x] **T-002** `[test]` (cubre RF-009) — Mismo archivo: mockear `invoke_model` para
  lanzar `ClientError` (`ResourceNotFoundException`); el `BedrockError` resultante
  contiene el `modelId` y la región configurados. Rojo (mensaje hoy es solo
  `str(e)`).
- [x] **T-003** `[code]` (cubre RF-009) — `image_client.py`, bloque `except Exception
  as e:`: el mensaje pasa a incluir `settings.BEDROCK_IMAGE_MODEL_ID` y `settings.
  BEDROCK_IMAGE_REGION`. Verde T-002; T-001 sigue verde.

## Bloque B — Tool `generate_image` (`tools.py`)

- [x] **T-010** `[test]` (cubre RF-007, retroactivo) — Nuevo
  `tests/unit/bedrock/test_generate_image_tool.py`: `purpose` inválido →
  `BedrockError` **sin** llamar a `image_client.generate_image_bytes` ni a
  `storage_service.upload_file` (mocks con `assert_not_called()`). Verde de
  inmediato.
- [x] **T-011** `[test]` (cubre RF-006) — Mismo archivo: `prompt` vacío/solo espacios
  → `BedrockError` **antes** de invocar `image_client.generate_image_bytes`
  (mockeado, `assert_not_called()`). Rojo.
- [x] **T-012** `[code]` (cubre RF-006) — `tools.py`, bloque `generate_image`: tras
  `resolve_purpose`, `prompt = (tool_input.get("prompt") or "").strip()`; `if not
  prompt: raise BedrockError(...)`; usar `prompt` (ya *stripeado*) en
  `generate_image_bytes` y en `description=prompt[:500]`. Verde T-011; T-010 sigue
  verde.
- [x] **T-013** `[test]` (cubre RF-010, retroactivo) — Mismo archivo:
  `storage_service.upload_file` mockeado para lanzar `Exception("boom")` (con
  `image_client.generate_image_bytes` mockeado a éxito) → `pytest.raises` y
  `db.add.assert_not_called()` / `db.commit.assert_not_called()`. Verde de
  inmediato.
- [x] **T-014** `[test]` (cubre RF-005, retroactivo) — Mismo archivo: con
  `image_client.generate_image_bytes` (bytes de un PNG mínimo real, para que
  `image_pipeline.finalize_png` no falle), `storage_service.upload_file` y
  `db: AsyncMock` mockeados a éxito → `execute_tool("generate_image", ...)` retorna
  `{"image_url", "filename", "purpose"}` y `db.add`/`db.commit` se llaman
  exactamente una vez cada uno. Verde de inmediato.

## Bloque C — Sesión del agente (`history_manager.py`)

- [x] **T-020** `[test]` (cubre RF-002, retroactivo) — Nuevo
  `tests/unit/bedrock/test_history_manager.py`: `append_message(db, "conv-123",
  "user", "hola")` con `db: AsyncMock` — se llama pasando el `str` plano, sin tocar
  ningún atributo `.id` de un objeto ORM (la firma ya no acepta `BedrockConversation`).
  Verde de inmediato.

## Bloque D — Readiness de MinIO

- [x] **T-030** `[test]` (cubre RF-008) — Nuevo `tests/unit/test_system_readiness.py`:
  con `storage_service.check_connection` mockeado `True` → `GET /system/readiness`
  responde `200` `{"status":"ready","checks":{"minio":true}}`; mockeado `False` →
  `503` `{"status":"not_ready","checks":{"minio":false}}`. Rojo (ni la función ni la
  ruta existen).
- [x] **T-031** `[code]` (cubre RF-008) — `storage_service.py`: `check_connection() ->
  bool` (`get_client().bucket_exists(settings.MINIO_BUCKET)`, `except S3Error:
  return False`). `app.py`: `GET /system/readiness` según
  `contracts/system-readiness.md`. Verde T-030.

## Bloque E — Migración `related_evidence_id`

- [x] **T-040** `[test]` (cubre RF-004) — Nuevo `tests/unit/test_file_upload_migration.py`.
  **Desviación del plan:** en vez de `TEST_DATABASE_URL` contra Postgres real, se
  siguió el patrón ya existente de `test_admin_section_migration.py` — `op`
  mockeado, aserción sobre el SQL emitido por `upgrade()`/`downgrade()` (contiene
  `FILE_UPLOADS`, `RELATED_EVIDENCE_ID`, `VARCHAR(20)`/`INTEGER` según el caso) y
  sobre `revision`/`down_revision`. Misma confianza, sin infra externa, consistente
  con el resto de migraciones de este repo (`file_uploads` tampoco tiene una
  migración de creación propia — predata Alembic). Rojo (la migración no existe).
- [x] **T-041** `[code]` (cubre RF-004) —
  `alembic/versions/e1f2a3b4c5d6_fix_file_upload_related_evidence_id_type.py`
  (`down_revision="c4d5e6f7a8b9"`): `upgrade()` → `ALTER TABLE file_uploads ALTER
  COLUMN related_evidence_id TYPE VARCHAR(20) USING related_evidence_id::varchar(20)`;
  `downgrade()` → `ALTER ... TYPE INTEGER USING NULLIF(related_evidence_id,
  '')::integer`. Verde T-040.

## Bloque F — Contrato de delegación (prompts)

- [x] **T-050** `[test]` (cubre RF-011) — Nuevo
  `tests/unit/bedrock/test_visual_delegation_prompts.py`: el `system_prompt_suffix`
  de `agent_professional_identity` menciona `purpose=proyectos`; el de
  `agent_digital_presence` menciona `purpose=publicaciones`; el de
  `agent_configuration` menciona `purpose=agentes`. Rojo.
- [x] **T-051** `[code]` (cubre RF-011) — `agent_profiles.py`: editar los tres
  `system_prompt_suffix` (tabla plan.md §1) para declarar el `purpose` de su
  dominio al delegar a `agent_visual_design`. Verde T-050.
- [x] **T-052** `[test]` (cubre RF-012) — Mismo archivo nuevo: el suffix de
  `AGENT_VISUAL_DESIGN` contiene una instrucción de pedir aclaración cuando el
  `purpose` no viene indicado o es ambiguo (no generar con un valor supuesto).
  Rojo.
- [x] **T-053** `[code]` (cubre RF-012) — `agent_profiles.py`, suffix de
  `AGENT_VISUAL_DESIGN`: añadir esa instrucción. Verde T-052.
- [x] **T-054** `[test]` (cubre D-8) — Mismo archivo nuevo: el suffix de
  `agent_search_operations` **no** contiene `"agent_visual_design"`. Rojo.
- [x] **T-055** `[code]` (cubre D-8) — `agent_profiles.py`: retirar "imágenes →
  agent_visual_design" del suffix de `agent_search_operations`. Verde T-054.

## Bloque G — Documentación (Art. 11)

- [x] **T-D1** `[doc]` — `docs/09-DECISIONS/025-migrar-generacion-imagenes-a-stability.md`
  (nuevo ADR): contexto (Titan EOL, Nova Canvas sin acceso), decisión (Stable Image
  Core en `us-west-2`), consecuencias, enlaza y enmienda `ADR-010`.
- [x] **T-D2** `[doc]` — Confirmado: `docs/ENVIRONMENT-SECURITY.md` línea 189 es un
  checklist genérico (`☐ BEDROCK_REGION/MODEL_ID: agregar si usas AWS Bedrock`), no
  enumera variables una a una. **No aplica** — sin cambio.
- [x] **T-D3** `[doc]` — `cjhirashi-career-api/src/services/bedrock/README.md`
  documentaba el pipeline con Titan (`width`/`height`, `taskType=TEXT_IMAGE`) —
  actualizado a Stability (`aspect_ratio`, formato de body/response), + nota del
  readiness check (RF-008) y el contrato de delegación del `purpose` (RF-011/012)
  en la sección "Nivel 2 — image_client.py".

## Bloque H — Cierre

- [x] **T-090** — `alembic upgrade head` ejecutado en el contenedor real
  (`career_db`): `c4d5e6f7a8b9` → `e1f2a3b4c5d6` (head); confirmado en vivo
  `information_schema.columns.related_evidence_id` = `character varying`.
  `GET /system/readiness` → `200 {"status":"ready","checks":{"minio":true}}`.
  Verificación end-to-end real (autorizada, Stable Image Core ~$0.01-0.04 USD):
  `execute_tool("generate_image", purpose="agentes", ...)` →
  `{"image_url": "https://files.cjhirashi.com/cjhirashi-career/public/agentes/
  verificacion-cierre-spec-002-e8fa2d33.png", "filename": "public/agentes/
  verificacion-cierre-spec-002-e8fa2d33.png", "purpose": "agentes"}` — fila
  `flu-15` insertada sin error de tipo (confirma RF-004 en producción), objeto
  confirmado en MinIO directo (`200`, `130134` bytes, `image/png`). Gate
  `./.harness/gate/check.sh --full` → **23 ok · 1 warn · 0 error** (warn =
  `anchor_commit` pendiente, se mueve al commitear). `anchor_commit` y
  `estado: verified` de `spec.md`/`plan.md`/`tasks.md` quedan pendientes del
  commit de cierre (aún sin commitear, pendiente de tu aprobación).

---

## Cobertura (el gate exige 100 %; `Estado` lo rellena el gate)

> Evidencia: `venv_test/bin/python -m pytest tests/unit/bedrock/test_image_client.py
> tests/unit/bedrock/test_generate_image_tool.py tests/unit/bedrock/test_history_manager.py
> tests/unit/test_system_readiness.py tests/unit/test_file_upload_migration.py
> tests/unit/bedrock/test_visual_delegation_prompts.py -v --no-cov` → **15 passed**
> (2026-09-04). Gate `./.harness/gate/check.sh --full` → **23 ok · 1 warn · 0 error**
> (warn = `anchor_commit` pendiente, normal antes del cierre).

| RF / doc | Tareas | Test(s) | Estado |
|---|---|---|---|
| RF-001 | T-001 | test_image_client::test_request_uses_configured_model_and_region | Pass |
| RF-002 | T-020 | test_history_manager::test_append_message_accepts_plain_id | Pass |
| RF-003 | — | sin test de código (D-3); resuelto operacionalmente, ver `state.md` | hecho |
| RF-004 | T-040, T-041 | test_file_upload_migration::test_upgrade_changes_column_to_varchar · ::test_downgrade_reverts_to_integer · ::test_revision_chains_linearly | Pass |
| RF-005 | T-014 | test_generate_image_tool::test_success_returns_expected_shape | Pass |
| RF-006 | T-011, T-012 | test_generate_image_tool::test_empty_prompt_rejected_before_bedrock | Pass |
| RF-007 | T-010 | test_generate_image_tool::test_invalid_purpose_rejected_before_anything | Pass |
| RF-008 | T-030, T-031 | test_system_readiness::test_ready_when_minio_ok · ::test_not_ready_when_minio_fails | Pass |
| RF-009 | T-002, T-003 | test_image_client::test_error_message_includes_model_and_region | Pass |
| RF-010 | T-013 | test_generate_image_tool::test_no_file_upload_row_when_minio_fails | Pass |
| RF-011 | T-050, T-051 | test_visual_delegation_prompts::test_delegating_profiles_state_purpose | Pass |
| RF-012 | T-052, T-053 | test_visual_delegation_prompts::test_visual_asks_when_purpose_ambiguous | Pass |
| D-8 | T-054, T-055 | test_visual_delegation_prompts::test_search_operations_no_longer_mentions_images | Pass |
| RNF-001 | T-090 | revisión manual: ninguna llamada real a Bedrock en T-001..T-055 (todas mockeadas, confirmado leyendo los 6 archivos de test); única llamada real en T-090, autorizada explícitamente antes de ejecutarse | Pass |
| doc: 025-ADR | T-D1 | `docs/09-DECISIONS/025-migrar-generacion-imagenes-a-stability.md` + enmienda en `010-bedrock-visual-pdf-agents.md` | hecho |
| doc: ENVIRONMENT-SECURITY.md | T-D2 | confirmado "no aplica" (checklist genérico) | hecho |
| doc: bedrock/README.md | T-D3 | sección "Nivel 2/3 — image_client.py" actualizada a Stability + readiness + contrato de delegación | hecho |
