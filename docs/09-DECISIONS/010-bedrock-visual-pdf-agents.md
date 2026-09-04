# ADR-010: Agentes agent_pdf_design y agent_visual_design

## Estado

Aceptado — 2026-08-16. Ampliado — 2026-08-26 (secciones de bucket por propósito, medidas fijas, flujo "guardar imagen existente", fix de bug en el cliente Titan). **Enmendado — 2026-09-04:** el modelo de generación de imágenes (Titan Image Generator) cambia a Stability Stable Image Core por retiro de Titan por parte de AWS — ver [ADR-025](./025-migrar-generacion-imagenes-a-stability.md).

## agent_pdf_design

Plantillas HTML en `pdf_output_templates`; tools CRUD + consulta por `agent_search_operations` / `agent_orchestrator`.

## agent_visual_design

L3, sin chat (mismas reglas de jerarquía de [ADR-012](./012-bedrock-three-level-agents.md)). Genera o guarda imágenes para tres áreas, cada una con su propia carpeta en el bucket MinIO y su propia medida fija — no hay tamaños libres:

| purpose | Carpeta bucket | Medida final | Uso |
|---|---|---|---|
| `agentes` | `public/agentes/` | 500x500 | Foto del catálogo de agentes (`BedrockAgentProfilePhoto`) |
| `proyectos` | `public/proyectos/` | 1920x1080 | `projects.image_url` |
| `publicaciones` | `public/publicaciones/` | 1920x1080 | `publications.image_url` |

Todo se guarda como **PNG**, recomprimido para web (`Pillow`, `optimize=True, compress_level=9`, sin pérdida). El agente pide/usa el prompt del solicitante, genera o procesa, nombra el archivo de forma legible (slug + sufijo corto para evitar colisiones) y responde con la `image_url` para que quien delegó la cargue en su registro.

### Dos flujos, dos tools

- **`generate_image`** (`prompt`, `purpose`, `name` opcional): genera con Titan Image Generator v2. Titan exige ancho/alto múltiplos de 64, así que se genera al múltiplo de 64 más cercano por abajo (p. ej. 500→448) y `image_pipeline.finalize_png()` ajusta (recorte centrado, sin deformar) a la medida exacta del `purpose` antes de subir.
- **`store_uploaded_image`** (`source_file_id`, `purpose`, `name` opcional): cuando el solicitante YA tiene una imagen (adjunta en el chat vía `file_id`, ver `attachments.py`) y solo quiere optimizarla/guardarla — sin generar nada nuevo. Lee los bytes originales de MinIO, aplica el mismo `finalize_png()` y sube al mismo lugar que `generate_image`. Mismo contrato de salida.

Ambas tools comparten `image_pipeline.py` (spec por `purpose`, ajuste Titan, recorte+recompresión PNG) — una sola fuente de verdad para tamaño/carpeta/compresión, sin duplicar lógica entre generar y guardar.

`attach_image_to_record` acepta `resource_key = publications | projects | agent-profile`; este último llama a `profile_photos.set_photo()` en vez de `update_career_record`, porque el catálogo de agentes no es un recurso de carrera (es código + un override en `BedrockAgentProfilePhoto`).

### Por qué

- Medida fija por propósito (no negociable en runtime) evita fotos de agente descuadradas en el catálogo o covers de proyecto con proporciones inconsistentes.
- PNG siempre (no JPEG condicional como el optimizador genérico de `/files`) porque el pedido es explícito y estas tres áreas priorizan nitidez sobre tamaño de archivo.
- Reusar `store_service.upload_file(..., name_hint=...)` en vez de bytes random-uuid: un nombre legible ayuda a auditar el bucket a simple vista; el sufijo uuid corto sigue garantizando que no haya colisiones.
- Un solo par de tools (generar / guardar) en vez de una tool por combinación purpose×origen: `purpose` es un parámetro, no una tool distinta — menos superficie para el modelo.

### Bug corregido (2026-08-26)

`image_client.py` tenía `_client = None` a nivel de módulo y `def _client():` con el mismo nombre — el `global _client` interno nunca creaba el cliente boto3 real (la condición `if _client is None` comprobaba la propia función, no el caché), así que **la generación de imágenes nunca había funcionado**. Renombrado a `_bedrock_client` (caché) / `_get_client()` (función). Junto con esto, `generate_image` tampoco insertaba una fila `FileUpload` — `list_generated_images` estaba siempre vacía; ahora ambas tools crean su fila.

## agent_digital_presence

Tools LinkedIn: publicar ahora, programar, eliminar programados.

## Referencias

- Pipeline: `api/src/services/bedrock/image_pipeline.py`
- Cliente Titan: `api/src/services/bedrock/image_client.py`
- Tools: `api/src/services/bedrock/tools.py` (`generate_image`, `store_uploaded_image`, `attach_image_to_record`, `list_generated_images`)
- Bucket: `api/src/services/storage_service.py` (`name_hint` en `upload_file`)
- Fotos de catálogo: `api/src/services/bedrock/profile_photos.py`
