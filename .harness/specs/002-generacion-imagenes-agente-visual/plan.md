---
titulo: Plan — Pipeline de generación de imágenes del agente Visual
tipo: plan
estado: verified
fecha: 2026-09-04
feature_id: "002"
spec: ./spec.md
---

# Plan de implementación (patrón por capas)

## 0 · Enfoque

Cadena de 4 causas raíz independientes en el mismo pipeline (`services/bedrock/*` →
`storage_service` → `models/file_upload.py`), más un ajuste de prompts de
delegación. Sin tabla nueva, sin endpoint de negocio nuevo — **sí** un endpoint de
sistema nuevo (`GET /system/readiness`, RF-008). Tres de las cuatro causas (RF-001,
RF-002, RF-003) ya tienen su corrección implementada y verificada manualmente en el
working tree; este plan las trata igual que al resto: con test retroactivo antes de
darlas por cerradas bajo el arnés.

Capas tocadas: **config → cliente externo (Bedrock, MinIO) → servicio (tools,
image_pipeline) → modelo/migración → prompts de agente (agent_profiles) → endpoint de
sistema**. Sin frontends tocados (el pipeline es 100% backend/agente).

## 1 · Fronteras y archivos por capa

| Capa | Archivo | Cambio |
|---|---|---|
| Config | `cjhirashi-career-api/src/config.py` | `BEDROCK_IMAGE_REGION` (nuevo) + `BEDROCK_IMAGE_MODEL_ID` default a Stability. *(ya hecho)* |
| Cliente Bedrock | `cjhirashi-career-api/src/services/bedrock/image_client.py` | Body/response formato Stability; cliente boto3 usa `BEDROCK_IMAGE_REGION`. *(ya hecho)* — **falta RF-009:** el `except` debe incluir `settings.BEDROCK_IMAGE_MODEL_ID` y `settings.BEDROCK_IMAGE_REGION` en el mensaje de `BedrockError`, no solo `str(e)`. |
| Pipeline de imagen | `cjhirashi-career-api/src/services/bedrock/image_pipeline.py` | `stability_aspect_ratio()` reemplaza `titan_generation_dims()`. *(ya hecho)* |
| Tool `generate_image` | `cjhirashi-career-api/src/services/bedrock/tools.py` | **RF-006 (falta):** validar `prompt.strip()` no vacío **antes** de `generate_image_bytes` (mismo bloque `if name == "generate_image":`, justo tras `resolve_purpose`). `purpose` inválido ya rechaza (RF-007, vía `resolve_purpose`). |
| Sesión del agente | `cjhirashi-career-api/src/services/bedrock/agent_loop.py`, `history_manager.py` | `conversation_id` como valor plano; `append_message(db, conversation_id: str, ...)`. *(ya hecho)* |
| Cliente MinIO | `cjhirashi-career-api/src/services/storage_service.py` | **RF-008 (falta):** nueva función `check_connection() -> bool` — `get_client().bucket_exists(settings.MINIO_BUCKET)`, `True` si autentica y el bucket existe, `False` si `S3Error` (cualquier código: credenciales, red, bucket ausente). No relanza. |
| Endpoint de sistema | `cjhirashi-career-api/src/app.py` | **RF-008 (falta):** `GET /system/readiness` — `{"status": "ready"\|"not_ready", "checks": {"minio": bool}}`, `200` si `ready`, `503` si no. Independiente de `/health` (ese sigue sin depender de MinIO — lo consumen el healthcheck de Docker y Caddy, y acoplarlo a MinIO ampliaría el radio de un blip transitorio). |
| Migración | `cjhirashi-career-api/alembic/versions/e1f2a3b4c5d6_fix_file_upload_related_evidence_id_type.py` (nuevo) | **RF-004 (falta):** `ALTER TABLE file_uploads ALTER COLUMN related_evidence_id TYPE VARCHAR(20) USING related_evidence_id::varchar(20)`. `down_revision = c4d5e6f7a8b9`. DDL puro, sin conversión de datos (D-4: 0 filas no-NULL). Naturalmente idempotente (再-aplicar sobre una columna ya `varchar(20)` no falla). No corre en `init_db` (`create_all` ya usa `String(20)` del modelo actual). |
| Modelo | `cjhirashi-career-api/src/models/file_upload.py` | Sin cambio de código — ya declara `Column(String(20))`; solo se actualiza el comentario si hace falta contexto sobre la migración de reconciliación. |
| Prompts — delegantes | `cjhirashi-career-api/src/services/bedrock/agent_profiles.py` | **RF-011 (falta):** `agent_professional_identity` (línea ~461) → "imágenes de un proyecto → agent_visual_design con purpose=proyectos"; `agent_digital_presence` (línea ~507) → "imágenes para publicaciones o el portal → agent_visual_design con purpose=publicaciones"; `_CONFIGURATION_SUFFIX` (agent_configuration, tras la línea de "fotos de agente") → añadir "Para generar una foto nueva de catálogo, delega con purpose=agentes". **D-8 (falta):** `agent_search_operations` (línea ~490) → retirar "imágenes → agent_visual_design" de su suffix. |
| Prompt — Visual (L3) | `cjhirashi-career-api/src/services/bedrock/agent_profiles.py` | **RF-012 (falta):** `AGENT_VISUAL_DESIGN` suffix (~línea 576) → añadir instrucción explícita: si quien delega no indica `purpose` o es ambiguo, responder pidiendo esa aclaración, no invocar `generate_image` con un valor supuesto. |

## 2 · Fronteras de salida

- **AWS Bedrock** (`bedrock-runtime`, `BEDROCK_IMAGE_REGION=us-west-2`) — sin cliente
  nuevo, mismo `boto3.client` de `image_client.py`, apuntando a otra región/modelo.
- **MinIO** (S3-compatible) — mismo cliente de `storage_service.py`; se le añade una
  operación de solo lectura (`bucket_exists`) para el readiness check, sin tocar el
  flujo de subida.
- **Postgres compartida** — vía Alembic, DDL puro sobre una columna existente.
- **Sistema (nuevo, no de negocio)** — `GET /system/readiness`, mismo patrón que
  `GET /health` y `POST /system/error-report` (sin prefijo de dominio, sin JWT: es
  para monitoreo/infra, igual que `/health`).

## 3 · Contratos y gates de CI

- `cjhirashi-career-api/openapi.yaml` **no existe** committeado → sin gate
  Spectral/oasdiff; el bloque `rest-http` corre la suite pytest.
- Nuevo `contracts/system-readiness.md` — request/response de `GET /system/readiness`
  (200 ready / 503 not_ready), como referencia humana y base del test de ruta.
- Sin contrato nuevo para Bedrock/MinIO: son fronteras externas (AWS/S3), no un
  contrato propio del proyecto — igual que el resto de `services/bedrock/*` hoy.
- Gate: `cd cjhirashi-career-api && venv_test/bin/python -m pytest -q`.
- **Art. 5:** ninguna llamada real a Bedrock en los tests nuevos — todas mockean
  `boto3`/`image_client.generate_image_bytes`. Las únicas llamadas reales ya se
  hicieron durante el diagnóstico (Fase 0), con evidencia pegada en `state.md`; no se
  repiten en Fase 4 salvo que el humano autorice una verificación final en vivo.

## 4 · Estrategia de pruebas por capa

| Capa | Archivo de test | Cubre |
|---|---|---|
| Cliente Bedrock (unit, boto3 mockeado) | `tests/unit/bedrock/test_image_client.py` (nuevo) | RF-001 (request a `BEDROCK_IMAGE_MODEL_ID`/`BEDROCK_IMAGE_REGION`, body `{prompt, aspect_ratio, output_format}`), RF-009 (mensaje de error incluye modelId + región ante `ResourceNotFoundException`/`AccessDeniedException` simulada). |
| Pipeline de imagen (unit, puro) | `tests/unit/bedrock/test_image_pipeline_aspect_ratio.py` | RF-001 (mapeo dimensión→aspect_ratio). *(ya existe, ya pasa)* |
| Sesión del agente (unit) | `tests/unit/bedrock/test_history_manager.py` (nuevo) | RF-002: `append_message(db, conversation_id: str, ...)` — llamado con un id de tipo `str` (nunca un objeto ORM), sin acceder a ningún atributo `.id`. |
| Tool `generate_image` (unit, dependencias mockeadas: `image_client`, `storage_service`, `db`) | `tests/unit/bedrock/test_generate_image_tool.py` (nuevo) | RF-005 (shape `{image_url, filename, purpose}` en éxito con todo mockeado a éxito), RF-006 (prompt vacío/espacios → `BedrockError` sin llamar a `image_client`), RF-007 (`purpose` inválido → `BedrockError` sin llamar a nada, retroactivo), RF-010 (`storage_service.upload_file` lanza → `db.add`/`db.commit` NO se llaman). |
| Readiness (unit, `TestClient` + `storage_service.check_connection` mockeado) | `tests/unit/test_system_readiness.py` (nuevo) | RF-008: `check_connection` mockeado `True` → `GET /system/readiness` 200 `{"status":"ready",...}`; mockeado `False` → 503 `{"status":"not_ready",...}`. |
| Migración (DB real vía `TEST_DATABASE_URL`, mismo patrón PG-only que el resto de la suite) | `tests/unit/test_file_upload_migration.py` (nuevo) | RF-004: tras `upgrade`, `information_schema.columns` reporta `related_evidence_id` como `character varying`; `downgrade` revierte a `integer`; `upgrade` de nuevo dos veces seguidas no falla (idempotente). Se salta si no hay `TEST_DATABASE_URL` (patrón ya usado por los tests PG-only existentes). |
| Prompts de delegación (unit, string assertions — mismo estilo que `test_profile_prompts.py`/`test_global_rules.py`) | `tests/unit/bedrock/test_visual_delegation_prompts.py` (nuevo) | RF-011: el `system_prompt_suffix` de `agent_professional_identity`/`agent_digital_presence`/`agent_configuration` menciona `purpose=` con el valor correcto de su dominio. RF-012: el suffix de `agent_visual_design` instruye a pedir aclaración si el `purpose` no está claro. D-8: `agent_search_operations` ya no menciona `agent_visual_design`. |

**TDD:** cada `RF-` con test en rojo primero (`@pytest.mark.requisito("RF-NNN")`),
luego el mínimo código, luego refactor. Para RF-001/RF-002/RF-003 (ya implementados)
el ciclo es inverso una sola vez: escribir el test contra el código ya existente,
confirmar que pasa en verde inmediatamente (es la trazabilidad retroactiva que pidió
Gate 1) — si alguno fallara, sería señal de que la corrección manual quedó incompleta.

## 5 · Secuenciación (test antes que código)

1. **RF-009** — test + mensaje de error con modelId/región en `image_client.py`.
2. **RF-006** — test + validación de `prompt` vacío en `tools.py`.
3. **RF-010** — test del orden subida-antes-que-insert en `tools.py` (sin cambio de
   código si el orden actual ya lo cumple; el test es lo que faltaba).
4. **RF-005 / RF-007** — test de shape de éxito y de `purpose` inválido (retroactivo).
5. **RF-001 / RF-002** — tests retroactivos contra el código ya corregido
   (`image_client.py`, `history_manager.py`).
6. **RF-008** — `storage_service.check_connection()` + `GET /system/readiness` + test.
7. **RF-003** — sin test de código (D-3); se documenta como resuelto operacionalmente
   en `state.md` (ya hecho) y queda cubierto por el monitoreo de RF-008 hacia
   adelante.
8. **RF-004** — migración Alembic + test contra `TEST_DATABASE_URL`.
9. **RF-011 / RF-012 / D-8** — ajustes de prompts en `agent_profiles.py` + test de
   contenido.
10. **Docs** (§ Impacto) + `alembic upgrade head` en el entorno real + verificación en
    vivo del pipeline completo (con autorización explícita del humano para la llamada
    real a Bedrock, Art. 5) + `anchor_commit` al commit de cierre.

## 6 · Implementación por RF

### RF-001 — modelo Bedrock con acceso vigente
*(ya implementado)* `config.py`: `BEDROCK_IMAGE_REGION="us-west-2"`,
`BEDROCK_IMAGE_MODEL_ID="stability.stable-image-core-v1:1"`. `image_client.py`:
`_get_client()` usa `BEDROCK_IMAGE_REGION`; `generate_image_bytes` manda
`{"prompt", "aspect_ratio", "output_format": "png"}`. `image_pipeline.py`:
`stability_aspect_ratio(spec)` mapea cada `PurposeSpec` al ratio fijo más cercano.
Test nuevo (`test_image_client.py`) mockea `boto3.client(...).invoke_model` y
verifica `modelId`/región/body — sin llamada real (Art. 5).

### RF-002 — aislar el fallo de una tool en delegación
*(ya implementado)* `agent_loop.py` línea ~507: `conversation_id: Optional[str]`
capturado apenas se crea/recupera la conversación. `history_manager.append_message`
recibe `conversation_id: str`. Test nuevo (`test_history_manager.py`) llama
`append_message` con un `str` plano contra un `AsyncSession` fake (o `TEST_DATABASE_URL`
si hace falta persistencia real) y confirma que no accede a ningún atributo de objeto.

### RF-003 — credenciales MinIO vigentes
*(ya resuelto operacionalmente, sin cambio de código)* `minio_storage` recreado
(`docker compose up -d --force-recreate --no-deps minio`) para que tome
`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` de `.env`. Verificado: `list_buckets()` con
credenciales de `.env` OK, `minioadmin` rechazado, 19+14 objetos intactos. Sin test de
código (D-3) — el mecanismo de detección hacia adelante es RF-008.

### RF-004 — `related_evidence_id` alineado al modelo
Migración `e1f2a3b4c5d6`: `op.execute("ALTER TABLE file_uploads ALTER COLUMN
related_evidence_id TYPE VARCHAR(20) USING related_evidence_id::varchar(20)")` en
`upgrade()`; `downgrade()` hace el `ALTER ... TYPE INTEGER USING
NULLIF(related_evidence_id, '')::integer` (best-effort; falla solo si alguien escribió
un valor no numérico después del upgrade, escenario que el modelo actual no produce).
Test contra `TEST_DATABASE_URL`: aplica la migración, confirma el tipo en
`information_schema.columns`, hace `downgrade`+`upgrade` y confirma que no revienta.

### RF-005 — éxito de punta a punta
`tools.py` ya arma `{"image_url", "filename", "purpose"}` sin cambios. Test nuevo
mockea `image_client.generate_image_bytes` (bytes de un PNG mínimo real, para que
`image_pipeline.finalize_png` no falle con Pillow), `storage_service.upload_file`
(retorna una key fija) y un `db: AsyncMock` — confirma el shape de retorno y que
`db.add`/`db.commit` se llamaron exactamente una vez.

### RF-006 — rechazo de `prompt` vacío antes de Bedrock
`tools.py`, bloque `if name == "generate_image":`: tras `spec =
image_pipeline.resolve_purpose(...)`, añadir `prompt = (tool_input.get("prompt") or
"").strip()` + `if not prompt: raise BedrockError("prompt vacío")`, y usar esa
variable `prompt` (ya *stripeada*) en la llamada a `generate_image_bytes` y en
`description=prompt[:500]`.

### RF-007 — `purpose` inválido *(retroactivo)*
Ya implementado vía `image_pipeline.resolve_purpose` (lanza `BedrockError` con los
valores válidos). Test nuevo confirma que ni `image_client` ni `storage_service` se
tocan cuando `purpose` es inválido.

### RF-008 — readiness de MinIO
`storage_service.check_connection() -> bool`: `try: return
get_client().bucket_exists(settings.MINIO_BUCKET) except S3Error: return False`.
`app.py`: `GET /system/readiness` — `ok = storage_service.check_connection()`;
`JSONResponse({"status": "ready" if ok else "not_ready", "checks": {"minio": ok}},
status_code=200 if ok else 503)`. Sin JWT (igual que `/health`). Test con
`TestClient` + `monkeypatch` de `check_connection`.

### RF-009 — mensaje de error con modelo y región
`image_client.py`, bloque `except Exception as e:`: el `BedrockError` pasa a
`f"Image generation failed (model={settings.BEDROCK_IMAGE_MODEL_ID}, "
f"region={settings.BEDROCK_IMAGE_REGION}): {e}"`. Test mockea `invoke_model` para
lanzar `ClientError` (`ResourceNotFoundException`) y confirma que el mensaje final
contiene el modelId y la región configurados.

### RF-010 — sin registro huérfano si la subida falla
Ya es el orden actual del código (`storage_service.upload_file` antes que
`db.add(FileUpload(...))`). Test nuevo: `storage_service.upload_file` mockeado para
lanzar; confirma `pytest.raises` y `db.add.assert_not_called()`.

### RF-011 — el delegante declara el `purpose`
`agent_profiles.py`: tres ediciones de texto (tabla §1) en los `system_prompt_suffix`
de `agent_professional_identity`, `agent_digital_presence` y `agent_configuration`,
cada una nombrando el `purpose` de su dominio explícitamente. Test de contenido de
string sobre `get_profile(id).system_prompt_suffix`.

### RF-012 — el Visual no adivina
`agent_profiles.py`, `AGENT_VISUAL_DESIGN` suffix: añadir "Si quien delega no te dice
`purpose` (agentes/proyectos/publicaciones) o no queda claro cuál aplica, pregunta
antes de generar — no asumas." Test de contenido de string.

### D-8 — `agent_search_operations` sin mención de imágenes
`agent_profiles.py` línea ~490: quitar "imágenes → agent_visual_design;" del
`system_prompt_suffix`. Test confirma que `"agent_visual_design"` no aparece en ese
suffix.

## § Impacto en documentación (Art. 11)

| Documento | Motivo | Tarea |
|---|---|---|
| `docs/BEDROCK-SYSTEM.md` | El subsistema de agentes cambia de proveedor de imagen (Titan→Stability) y de región | *(ya actualizado)* — `[doc]` de verificación, sin cambio adicional |
| `docs/09-DECISIONS/025-migrar-generacion-imagenes-a-stability.md` (nuevo ADR) | Decisión arquitectónica: reemplazo del proveedor/modelo de generación de imagen que amplía/corrige `ADR-010` (EOL de Titan, sin acceso a Nova Canvas) | `[doc]` — redactar el ADR |
| `docs/ENVIRONMENT-SECURITY.md` | Nueva variable `BEDROCK_IMAGE_REGION` | `[doc]` — añadir a la lista de variables Bedrock si el documento las enumera individualmente (hoy es un checklist genérico; confirmar si aplica) |
| `cjhirashi-career-api/src/services/bedrock/README.md` (si existe y documenta `generate_image`) | Contrato de delegación (RF-011/012) y el readiness check (RF-008) | `[doc]` — verificar si el README menciona el pipeline de imagen; actualizar si sí |

## 7 · `covers` definitivo (para el front-matter de `spec.md`)

```yaml
covers:
  - cjhirashi-career-api/src/config.py
  - cjhirashi-career-api/src/services/bedrock/agent_loop.py
  - cjhirashi-career-api/src/services/bedrock/history_manager.py
  - cjhirashi-career-api/src/services/bedrock/image_client.py
  - cjhirashi-career-api/src/services/bedrock/image_pipeline.py
  - cjhirashi-career-api/src/services/bedrock/tools.py
  - cjhirashi-career-api/src/services/bedrock/agent_profiles.py
  - cjhirashi-career-api/src/services/storage_service.py
  - cjhirashi-career-api/src/app.py
  - cjhirashi-career-api/src/models/file_upload.py
  - cjhirashi-career-api/alembic/versions/e1f2a3b4c5d6_*.py
  - cjhirashi-career-api/tests/unit/bedrock/test_image_client.py
  - cjhirashi-career-api/tests/unit/bedrock/test_image_pipeline_aspect_ratio.py
  - cjhirashi-career-api/tests/unit/bedrock/test_history_manager.py
  - cjhirashi-career-api/tests/unit/bedrock/test_generate_image_tool.py
  - cjhirashi-career-api/tests/unit/bedrock/test_visual_delegation_prompts.py
  - cjhirashi-career-api/tests/unit/test_system_readiness.py
  - cjhirashi-career-api/tests/unit/test_file_upload_migration.py
  - docker-compose.yml
  - .env.example
  - docs/BEDROCK-SYSTEM.md
  - docs/09-DECISIONS/025-migrar-generacion-imagenes-a-stability.md
  - docs/ENVIRONMENT-SECURITY.md
  - .harness/specs/002-generacion-imagenes-agente-visual/contracts/system-readiness.md
```
