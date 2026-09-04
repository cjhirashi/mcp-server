---
titulo: Pipeline de generación de imágenes del agente Visual (generate_image)
tipo: spec
estado: specified
fecha: 2026-09-04
feature_id: "002"
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
anchor_mode: advisory
---

# Pipeline de generación de imágenes del agente Visual (generate_image)

## 1 · Contexto del dominio

**Problema (una frase):** el tool `generate_image` del agente L3 Visual
(`agent-10`/`agent_visual_design`) falla de punta a punta — el usuario pide una imagen
y no la recibe — por una cadena de 4 causas raíz independientes descubiertas mediante
diagnóstico en vivo (`error_reports` `err-50/51/52` + reproducción real):

1. **Bedrock:** Titan Image Generator (v1 y v2) llegó a fin de vida
   (`ResourceNotFoundException`); `amazon.nova-canvas-v1:0` está `Legacy` y sin acceso
   habilitado para esta cuenta en `us-east-1`.
2. **Sesión del agente:** una tool que falla dentro de `delegate_to_specialist`
   (misma `AsyncSession`) dispara un `db.rollback()` defensivo que expira todos los
   objetos de la sesión, incluida `conversation`; tocar `conversation.id` (atributo
   expirado) fuera de un `await` revienta el turno completo del agente delegante con
   `MissingGreenlet`.
3. **MinIO:** el contenedor `minio_storage` corre con las credenciales *default* de la
   imagen (`minioadmin`), desincronizadas de las credenciales declaradas en `.env` que
   usa `cjhirashi-career-api` — el upload falla con `InvalidAccessKeyId`.
4. **Esquema Postgres:** `file_uploads.related_evidence_id` es `integer` en la base de
   datos real, pero el modelo ORM (`models/file_upload.py`) lo declara `String(20)`
   desde siempre — el `INSERT` final revienta con `DatatypeMismatchError`.

Las causas 1–3 ya tienen una corrección implementada y verificada manualmente (sin
commitear); la causa 4 está pendiente de diseño (Fase 2) e implementación (Fase 4).
Esta spec cubre las **4** como un solo pipeline, dándoles trazabilidad `RF-`/test
retroactiva.

**Límites / dependencias de infra:**
- Servicio dueño: `cjhirashi-career-api` (`services/bedrock/*`, Alembic, MinIO client).
- Fronteras externas: AWS Bedrock (`bedrock-runtime`), MinIO (S3-compatible), Postgres
  compartida.
- **Fuera de los límites de este repo:** el 403 observado en
  `https://files.cjhirashi.com/...` al servir objetos públicos de MinIO es un problema
  de la capa Caddy (`cjhirashi-srv`) — confirmado que MinIO sirve el objeto
  correctamente en directo (200) y solo falla a través del proxy. No se toca aquí; se
  gestiona con un mensaje nuevo en `caddy.json` fuera de esta feature.

## 2 · Alcance

### En alcance
- Reemplazar el modelo/región de generación de imagen para que la tool funcione con
  una cuenta AWS que ya no tiene acceso a Titan/Nova Canvas.
- Aislar el fallo de una tool dentro de una delegación para que no reviente el turno
  completo del agente delegante.
- Que las credenciales con las que `cjhirashi-career-api` autentica contra MinIO sean
  siempre las vigentes en configuración, con una forma de detectar la desincronización
  antes de que falle un upload real.
- Alinear el tipo de `file_uploads.related_evidence_id` en Postgres con el modelo ORM.
- Validaciones de entrada de `generate_image` (prompt vacío, `purpose` inválido) antes
  de invocar Bedrock.
- Trazabilidad retroactiva (RF- + test) de las 3 causas ya corregidas.
- Contrato de delegación explícito: el agente que solicita una imagen (L1/L2) DEBE
  indicar el `purpose` según su dominio; el agente Visual (L3) NO DEBE adivinarlo si
  no viene claro en la delegación. Incluye retirar la mención genérica "imágenes →
  agent_visual_design" de `agent_search_operations` (su dominio no tiene ningún
  recurso de imagen).

### Fuera de alcance
- El 403 de `files.cjhirashi.com` vía Caddy (no es código de este repo).
- Lógica de compensación/rollback si el `INSERT` en `file_uploads` falla **después**
  de un upload exitoso a MinIO (huérfano) — RF-004 elimina la causa que lo provoca;
  añadir compensación sería código defensivo para un escenario que deja de ocurrir
  (Art. 10, regla de raíz).
- Reintentos automáticos ante fallos transitorios de Bedrock (throttling, timeouts).
- Cambiar `store_uploaded_image` (guardar una imagen ya existente) — no pasa por
  generación en Bedrock, no comparte las causas 1/2 de este pipeline (sí comparte 3 y
  4, que se corrigen igual para toda la tabla `file_uploads`).
- Elegir un modelo de imagen distinto a Stable Image Core (ya decidido con el humano
  en el diagnóstico previo).

## 3 · Modelo de datos y contratos de E/S

### 3.1 Frontera de entrada — tool `generate_image`
Sin cambios de forma (ya está en `tools.py`):
```json
{
  "prompt": "string, requerido",
  "purpose": "agentes | proyectos | publicaciones",
  "name": "string, opcional"
}
```
Nuevo: `prompt` vacío o solo espacios se rechaza **antes** de invocar Bedrock
(RF-006).

### 3.2 Frontera de salida — AWS Bedrock (`bedrock-runtime`)
- **Región:** `BEDROCK_IMAGE_REGION` (nueva, separada de `BEDROCK_REGION` que sigue
  sirviendo Converse/embeddings) = `us-west-2`.
- **Modelo:** `BEDROCK_IMAGE_MODEL_ID` = `stability.stable-image-core-v1:1`.
- **Request:** `{"prompt": str, "aspect_ratio": "1:1"|"16:9"|…, "output_format": "png"}`
  — reemplaza el formato Titan (`taskType`/`textToImageParams`/`width`/`height`).
- **Response:** `{"images": [base64], "seeds": [...], "finish_reasons": [...]}`.
- **Mapeo dimensión→aspect_ratio:** cada `PurposeSpec` (500×500 agentes, 1920×1080
  proyectos/publicaciones) se traduce al `aspect_ratio` fijo más cercano; el recorte a
  la medida exacta lo sigue haciendo `image_pipeline.finalize_png` después.

### 3.3 Frontera de salida — MinIO
- Bucket `cjhirashi-career`, prefix `public/{purpose}/`.
- Credenciales: `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` de `.env`, las mismas para el
  contenedor `minio_storage` y para `cjhirashi-career-api` (`storage_service.py`).
- Nuevo: un mecanismo de verificación (readiness) que confirme, en el propio proceso
  de la API, que las credenciales configuradas autentican contra el MinIO real
  (RF-008) — el diseño concreto (endpoint, frecuencia) lo fija Fase 2.

### 3.4 Persistencia — `file_uploads`
- `related_evidence_id`: cambia de `INTEGER` a `VARCHAR(20)` en Postgres para igualar
  `models/file_upload.py` (`Column(String(20))`, sin cambios — nunca se escribió desde
  código, hoy 0 filas no-`NULL` de 12). Migración Alembic **DDL puro**, sin conversión
  de datos (se asume `NULL` en todo entorno donde corra).

### 3.5 Salida de la tool en éxito
Sin cambios de forma: `{"image_url": str, "filename": str, "purpose": str}`.

### 3.6 Contrato de delegación — quién declara el `purpose`
`delegate_to_specialist` es de un solo golpe (`task`/`context` en texto libre; el
sub-turno del especialista corre y devuelve un resultado — no hay ida y vuelta
conversacional L2↔L3 dentro del mismo turno). El `purpose` no puede quedar implícito:

| Agente delegante (L1/L2) | Dominio dueño | `purpose` que DEBE declarar |
|---|---|---|
| `agent_professional_identity` | recurso `projects` | `proyectos` |
| `agent_digital_presence` | publicaciones del portal / redes | `publicaciones` |
| `agent_configuration` | catálogo de agentes (fotos de perfil) | `agentes` |

`agent_search_operations` no tiene ningún recurso de imagen en su dominio (búsqueda/
vacantes); su mención genérica "imágenes → agent_visual_design" se retira (no debe
delegar generación de imágenes).

### 3.7 Errores
| Situación | Comportamiento requerido |
|---|---|
| Modelo Bedrock sin acceso/inexistente | Mensaje que identifique modelo y región, no genérico (RF-009) |
| Tool falla dentro de una delegación | El turno del delegante continúa; solo esa tool reporta el fallo (RF-002) |
| `prompt` vacío | Rechazo antes de invocar Bedrock, sin cargo (RF-006) |
| `purpose` inválido | Rechazo antes de generar nada (RF-007, ya implementado) |
| Delegación de imagen sin `purpose` claro | El agente Visual responde pidiendo la aclaración, no genera (RF-012) |

## 4 · Criterios de aceptación (EARS)

- **RF-001** — CUANDO el agente Visual invoca `generate_image` con un `purpose`
  válido, el sistema DEBE generar la imagen contra un modelo Bedrock con acceso
  vigente en la cuenta configurada (`BEDROCK_IMAGE_MODEL_ID` en `BEDROCK_IMAGE_REGION`).
- **RF-002** — SI una tool falla dentro de una delegación (`delegate_to_specialist`,
  misma `AsyncSession`) ENTONCES el sistema DEBE reportar el fallo de esa tool sin
  interrumpir con un error genérico el resto del turno del agente delegante.
- **RF-003** — El sistema DEBE autenticar contra MinIO con las credenciales vigentes
  de `.env`, no con las credenciales *default* de la imagen del contenedor.
- **RF-004** — CUANDO se inserta un `file_uploads` con `related_evidence_id` nulo, el
  sistema DEBE completar el `INSERT` sin error de tipo de dato.
- **RF-005** — CUANDO `generate_image` completa con éxito, el sistema DEBE devolver
  una `image_url` pública y persistir el registro correspondiente en `file_uploads`.
- **RF-011** — CUANDO `agent_professional_identity`, `agent_digital_presence` o
  `agent_configuration` delegan una solicitud de imagen a `agent_visual_design`, el
  agente delegante DEBE declarar explícitamente el `purpose` correspondiente a su
  dominio (`proyectos`, `publicaciones` y `agentes` respectivamente) en el `task` de
  la delegación.
- **RF-012** — SI el agente Visual recibe una delegación de imagen sin que el
  `purpose` esté indicado o sea ambiguo ENTONCES DEBE responder solicitando esa
  aclaración en vez de invocar `generate_image` con un `purpose` supuesto.

## 5 · Casos límite y manejo de errores

- **RF-006** — SI el `prompt` de `generate_image` está vacío o contiene solo espacios
  ENTONCES el sistema DEBE rechazar la solicitud antes de invocar Bedrock.
- **RF-007** *(retroactivo, ya implementado)* — SI `purpose` no es uno de
  `agentes|proyectos|publicaciones` ENTONCES el sistema DEBE rechazar la solicitud con
  un error claro antes de generar o subir nada.
- **RF-008** — El sistema DEBE exponer un mecanismo de verificación (readiness) que
  confirme que las credenciales configuradas autentican correctamente contra MinIO.
- **RF-009** — SI el modelo de imagen configurado no está disponible
  (`ResourceNotFoundException`/`AccessDeniedException`) ENTONCES el sistema DEBE
  fallar con un mensaje que identifique el `modelId` y la región usados, no un error
  genérico.
- **RF-010** — SI la subida a MinIO falla (por cualquier causa) ENTONCES el sistema NO
  DEBE crear un registro en `file_uploads` para esa generación.

## 6 · Registro de decisiones y descartes

| # | Decisión | Porqué | Descartado |
|---|---|---|---|
| D-1 | Una sola spec cubre las 4 causas como un pipeline | Comparten el mismo criterio de aceptación observable ("el usuario pide una imagen y la recibe"); da trazabilidad retroactiva a 3 causas ya corregidas sin arnés | Spec separada solo para la causa 4 (esquema), dejando 1–3 sin `RF-`/test |
| D-2 | Reemplazo de modelo: Stability `stable-image-core-v1:1` en `us-west-2` | Único con acceso ya habilitado en esta cuenta sin trámite en consola AWS; costo/calidad adecuado para el uso (decisión ya tomada con el humano) | SD3.5 Large / Stable Image Ultra (más caros); esperar habilitación de Nova Canvas en consola |
| D-3 | RF-008 (readiness MinIO) en vez de solo runbook | La suite actual no puede probar credenciales reales; un chequeo automático detecta la desincronización antes de que falle un usuario real — es lo que realmente pasó aquí | Documentar solo como invariante operacional sin gate automático |
| D-4 | Migración de `related_evidence_id` sin lógica de conversión de datos | 0 filas no-`NULL` de 12, ninguna ruta de código escribe este campo nunca | Migración que además castee/preserve valores enteros existentes |
| D-5 | Huérfano en MinIO tras un `INSERT` fallido: fuera de alcance, sin compensación | RF-004 elimina la causa raíz que lo provoca; compensación sería código defensivo para un escenario que ya no ocurre (Art. 10) | `RF-` de limpieza/compensación automática de objetos huérfanos |
| D-6 | El 403 de `files.cjhirashi.com` queda fuera de este repo | Confirmado que es la capa Caddy (`cjhirashi-srv`), no MinIO ni este código; protocolo del proyecto es `caddy.json` + `bin/caddy-msg`, no tocar `cjhirashi-srv` | Investigar/corregir la config de Caddy desde aquí |
| D-7 | El `purpose` de una imagen lo declara el agente delegante según su dominio (tabla §3.6), no lo infiere el agente Visual | Cada dominio conoce el uso real de la imagen; `delegate_to_specialist` es de un solo golpe, sin ida y vuelta para preguntar en vivo | Que el agente Visual infiera el `purpose` del texto de la tarea |
| D-8 | Retirar la mención "imágenes → agent_visual_design" de `agent_search_operations` | Su dominio (búsqueda/vacantes) no posee ningún recurso de imagen; dejarla es una ruta de ambigüedad sin dueño claro de `purpose` | Dejarla como está (inofensiva pero ambigua) |

## 7 · Requisitos no funcionales

- **RNF-001** — Toda llamada de prueba real a Bedrock durante la Fase 4 (validación)
  DEBE pedirse con autorización explícita del humano antes de ejecutarse, y su costo
  estimado se registra antes de invocarla (Constitución Art. 5).
