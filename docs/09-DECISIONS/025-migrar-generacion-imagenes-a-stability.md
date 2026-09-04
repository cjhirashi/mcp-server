# ADR-025: Migrar la generación de imágenes de Titan a Stability Stable Image Core

## Estado

Aceptado — 2026-09-04

Enmienda [ADR-010](./010-bedrock-visual-pdf-agents.md) (elección original del
modelo de generación de imágenes del agente Visual).

## Contexto

El tool `generate_image` del agente L3 Visual (`agent-10`/`agent_visual_design`)
generaba imágenes con **Titan Image Generator** (v1 y v2) en `us-east-1`
(`BEDROCK_IMAGE_MODEL_ID`, decisión original de ADR-010). Diagnosticando reportes
reales de falla (`error_reports` `err-50/51/52`) se confirmó invocando ambos
`modelId` directo:

- `amazon.titan-image-generator-v1` y `amazon.titan-image-generator-v2:0` →
  `ResourceNotFoundException: This model version has reached the end of its life.`
  AWS retiró Titan Image Generator por completo.
- `amazon.nova-canvas-v1:0` (el reemplazo sugerido por AWS) resuelve como modelo
  pero está marcado `Legacy` y sin acceso habilitado para esta cuenta en
  `us-east-1` (`Access denied... marked as Legacy`).

Se investigó qué modelos de imagen sí tienen acceso activo en la cuenta, probando
otras regiones. `us-west-2` (a diferencia de `us-east-1`) sí ofrece y tiene acceso
concedido a la familia de modelos de imagen de Stability AI con generación
texto-a-imagen: `stability.stable-image-core-v1:1`, `stability.sd3-5-large-v1:0` y
`stability.stable-image-ultra-v1:1` — confirmado invocando los tres en vivo
(`invoke_model` responde `200` con imagen generada). Ninguno requirió trámite en la
consola de AWS Bedrock (Model access).

## Decisión

**Reemplazar Titan Image Generator por `stability.stable-image-core-v1:1` en
`us-west-2`** como modelo de generación de imágenes del agente Visual.

- Nueva variable `BEDROCK_IMAGE_REGION=us-west-2`, separada de `BEDROCK_REGION`
  (`us-east-1`, sigue sirviendo Converse y embeddings Titan — esos no están
  afectados por el retiro de Titan Image).
- `BEDROCK_IMAGE_MODEL_ID` cambia su default a `stability.stable-image-core-v1:1`.
- El contrato de request/response de `image_client.py` cambia al formato Stability
  (`{"prompt", "aspect_ratio", "output_format"}` → `{"images": [base64], ...}`),
  reemplazando el formato Titan (`taskType`/`textToImageParams`/`width`/`height`).
- `image_pipeline.stability_aspect_ratio()` reemplaza `titan_generation_dims()`:
  mapea cada `PurposeSpec` (500×500 agentes, 1920×1080 proyectos/publicaciones) al
  `aspect_ratio` fijo más cercano que acepta el modelo; el recorte a la medida
  exacta lo sigue haciendo `image_pipeline.finalize_png` después — sin cambio en
  esa capa.

### Por qué Stable Image Core y no SD3.5 Large / Stable Image Ultra

Los tres tienen acceso activo. Se eligió Core por costo/calidad adecuados al uso
actual (fotos de catálogo de agentes, banners de proyectos/publicaciones) —
decisión tomada con el humano durante el diagnóstico. SD3.5 Large y Stable Image
Ultra quedan como alternativas si la calidad de Core resulta insuficiente para un
uso futuro.

### Por qué no esperar a que AWS habilite Nova Canvas

Nova Canvas sigue apareciendo como modelo pero con acceso denegado y marcado
`Legacy` por el proveedor — no hay garantía ni plazo de que AWS lo habilite para
esta cuenta, y el pipeline estaba roto en producción. Stable Image Core ya
funciona hoy sin gestión adicional.

## Consecuencias

### Positivas

- El pipeline de generación de imágenes vuelve a funcionar sin esperar ninguna
  acción manual en la consola de AWS.
- Región de imagen desacoplada de la región de Converse/embeddings — un futuro
  cambio de modelo de imagen no obliga a mover el resto del harness Bedrock.

### Negativas / a asumir

- Dos regiones AWS Bedrock en juego (`us-east-1` para Converse/embeddings,
  `us-west-2` para imagen) en vez de una — más superficie de configuración
  (`BEDROCK_IMAGE_REGION`) a mantener sincronizada en `.env`/`docker-compose.yml`.
- El formato de request/response de Stability es distinto al de Titan; cualquier
  código futuro que asuma el formato Titan (ninguno detectado fuera de
  `image_client.py`/`image_pipeline.py`) debe actualizarse.

## Alternativas consideradas

### Esperar habilitación de Nova Canvas en la consola AWS

- Contra: sin plazo garantizado; el pipeline seguiría roto mientras tanto.

### Mantener Titan e ignorar el error

- Contra: Titan v1 y v2 están retirados por AWS de forma permanente
  (`ResourceNotFoundException` — no es un fallo transitorio).

## Implicaciones

- [x] `config.py`: `BEDROCK_IMAGE_REGION` nuevo; `BEDROCK_IMAGE_MODEL_ID` default a
      Stability.
- [x] `image_client.py`: formato de request/response Stability.
- [x] `image_pipeline.py`: `stability_aspect_ratio()`.
- [x] `docker-compose.yml`, `.env.example`, `docs/BEDROCK-SYSTEM.md`,
      `services/bedrock/README.md` actualizados.
- [x] Referencias a "Titan" retiradas de `tools.py`/`agent_profiles.py`.

## Seguimiento

Ver spec `.harness/specs/002-generacion-imagenes-agente-visual/spec.md` (RF-001,
RF-009) para la trazabilidad de test de este cambio.

---

**Creado por**: Arquitecto de Soluciones
**Aprobado por**: Carlos Jiménez Hirashi
**Fecha de creación**: 2026-09-04
**Última revisión**: 2026-09-04
**Estado de vigencia**: Vigente
