"""
Tools Converse — schemas y ejecución (CRUD, LinkedIn, PDF, imágenes, web, GitHub).

Tier 1: career CRUD (delegado a bedrock_service._execute_tool).
Tier 2: LinkedIn, plantillas PDF, estilos CSS, imágenes, vacantes, consulta web, GitHub, delegación.
Ver api/docs/BEDROCK-HARNESS.md.
"""
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import desc, select

from config import settings
from models.linkedin_connection import LinkedInConnection
from models.linkedin_post import LinkedInPost, LinkedInPostStatus
from models.pdf_output_template import PdfOutputTemplate
from models.pdf_template_style import PdfTemplateStyle
from repositories.career_repository import CareerRepository
from services import bedrock_service, storage_service
from services.id_generator import normalize_prefixed_id
from services.bedrock.errors import BedrockError
from services.bedrock.tool_results import truncate_tool_result

_PDF_STYLE_REPO = CareerRepository(PdfTemplateStyle, resource_key="pdf-template-styles", vectorize=False)
_PDF_STYLE_UPDATE_FIELDS = {"slug", "title", "description", "css_content", "style_guide", "is_active"}


def merge_writable_fields(tool_input: Dict[str, Any], allowed: Set[str]) -> Dict[str, Any]:
    """Collect writable keys from nested `fields` and the top level.

    Create uses top-level properties (`style_guide`, `css_content`, …). Models
    often update the same way; requiring a nested `fields` object dropped the
    payload and the agent then claimed success in chat without writing.
    Top-level values override nested ones when both are present.
    """
    merged: Dict[str, Any] = {}
    nested = tool_input.get("fields")
    if isinstance(nested, dict):
        for key, value in nested.items():
            if key in allowed:
                merged[key] = value
    for key in allowed:
        if key in tool_input and tool_input[key] is not None:
            merged[key] = tool_input[key]
    return merged

# ============================================================================
# Parámetros compartidos de schemas
# ============================================================================

_RESOURCE_KEY_PARAM = {
    "type": "string",
    "description": "resource_key, ej. vacancies, publications, projects",
}

_RECORD_ID_PARAM = {
    "type": "string",
    "description": "ID prefijado del registro, ej. ach-17, cmp-42, vac-7. Usar el id completo.",
}

# ============================================================================
# Schemas de tools Converse
# ============================================================================

# Schemas Converse (toolSpec.inputSchema.json)
_RAW_TOOLS: List[Dict[str, Any]] = [
    {"name": "list_recent_changes", "description": "Bitácora reciente del agente.", "schema": {"type": "object", "properties": {"resource_key": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "restore_deleted_record", "description": "Restaura un delete desde audit_id.", "schema": {"type": "object", "properties": {"audit_id": {"type": "integer"}}, "required": ["audit_id"]}},
    {"name": "describe_resource_schema", "description": "Campos válidos de un resource_key.", "schema": {"type": "object", "properties": {"resource_key": _RESOURCE_KEY_PARAM}, "required": ["resource_key"]}},
    {"name": "search_knowledge_base", "description": "Búsqueda semántica Qdrant. Con type=methodology SOLO devuelve metodologías asignadas a tu perfil (agent_profile_ids) o compartidas (lista vacía). El guardián agent_methodologies ve todas. NO usar para 'lista todos mis X' — usa list_career_record.", "schema": {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}, "type": {"type": "string", "enum": ["methodology", "career_record"]}}, "required": ["query"]}},
    {"name": "list_career_record", "description": "Lista registros paginados (vista compacta: id, title, summary). Para 'lista todos mis X' usa limit=100 sin search (no search_knowledge_base). Incluye TODOS los items; revisa total_count y pagina si has_more. Si necesitas revisar una columna puntual (ej. nivel, category) en TODOS los registros de un resource_key, pasa fields=['esa_columna'] aquí en vez de llamar get_career_record uno por uno — un solo list_career_record con fields trae esa columna en cada item de la página.", "schema": {"type": "object", "properties": {"resource_key": _RESOURCE_KEY_PARAM, "search": {"type": "string"}, "limit": {"type": "integer"}, "skip": {"type": "integer"}, "fields": {"type": "array", "items": {"type": "string"}, "description": "Opcional. Columnas extra a incluir en cada item de la lista, además de id/title/summary."}}, "required": ["resource_key"]}},
    {"name": "count_career_records", "description": "Cuenta registros de un resource_key. Usar para '¿cuántos X tengo?'.", "schema": {"type": "object", "properties": {"resource_key": _RESOURCE_KEY_PARAM, "search": {"type": "string"}}, "required": ["resource_key"]}},
    {"name": "get_career_record", "description": "Obtiene un registro por id. En registros grandes (p.ej. projects, cv-versions) pasa 'fields' con solo las columnas que necesitas para no traer todo el registro; el id siempre se incluye. Si no sabes los nombres exactos, usa describe_resource_schema primero.", "schema": {"type": "object", "properties": {"resource_key": _RESOURCE_KEY_PARAM, "record_id": _RECORD_ID_PARAM, "fields": {"type": "array", "items": {"type": "string"}, "description": "Opcional. Columnas a devolver (id siempre incluido)."}}, "required": ["resource_key", "record_id"]}},
    {"name": "create_career_record", "description": "Crea registro. Escribir el contenido en el chat NO guarda: llama esta tool con resource_key y fields.", "schema": {"type": "object", "properties": {"resource_key": _RESOURCE_KEY_PARAM, "fields": {"type": "object"}}, "required": ["resource_key", "fields"]}},
    {"name": "update_career_record", "description": "Actualiza registro. Escribir el contenido en el chat NO guarda: llama esta tool con resource_key, record_id y fields.", "schema": {"type": "object", "properties": {"resource_key": _RESOURCE_KEY_PARAM, "record_id": _RECORD_ID_PARAM, "fields": {"type": "object"}}, "required": ["resource_key", "record_id", "fields"]}},
    {
        "name": "bulk_update_career_record",
        "description": (
            "Actualiza VARIOS registros del mismo resource_key en una sola llamada "
            "(ej. reclasificar todas las competencias en 4 categorías). Úsala en vez de "
            "llamar update_career_record una por una cuando el cambio toca varias filas. "
            "updates es una lista de {record_id, fields}; máximo 200 por llamada, pero si son "
            "más de ~25-30 registros o los fields llevan texto largo, mándalos en varias "
            "llamadas de ~20-25 items cada una (una tras otra, en el mismo turno) en vez de un "
            "solo payload gigante — evita cortes por límite de tokens de salida a mitad de la "
            "respuesta. Escribirlo en el chat NO guarda nada — llama esta tool."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "resource_key": _RESOURCE_KEY_PARAM,
                "updates": {
                    "type": "array",
                    "description": "Cada item: {record_id, fields}. fields son las columnas a cambiar en ese registro.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "record_id": _RECORD_ID_PARAM,
                            "fields": {"type": "object"},
                        },
                        "required": ["record_id", "fields"],
                    },
                },
            },
            "required": ["resource_key", "updates"],
        },
    },
    {"name": "delete_career_record", "description": "Elimina registro.", "schema": {"type": "object", "properties": {"resource_key": _RESOURCE_KEY_PARAM, "record_id": _RECORD_ID_PARAM}, "required": ["resource_key", "record_id"]}},
    {"name": "get_linkedin_status", "description": "Estado conexión LinkedIn.", "schema": {"type": "object", "properties": {}}},
    {"name": "list_linkedin_posts", "description": "Cola e historial posts LinkedIn.", "schema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "create_linkedin_post", "description": "Publicar ahora (sin scheduled_at) o programar (ISO futuro).", "schema": {"type": "object", "properties": {"text": {"type": "string"}, "image_url": {"type": "string"}, "scheduled_at": {"type": "string"}}, "required": ["text"]}},
    {"name": "delete_scheduled_linkedin_post", "description": "Elimina post status=scheduled.", "schema": {"type": "object", "properties": {"post_id": {"type": "string", "description": "ID prefijado, ej. lnp-3"}}, "required": ["post_id"]}},
    {"name": "pdf_template", "description": "CRUD de pdf_output_templates (HTML, IDs pdt-N). No edita CSS. action=list|get|create|update. create requiere slug, document_type, title, html_template. update requiere template_id y los campos a cambiar (html_template, style_id, variables, …) en el nivel superior o en fields. Escribir HTML en el chat NO guarda.", "schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["list", "get", "create", "update"]}, "template_id": {"type": "string", "description": "ID prefijado, ej. pdt-1"}, "slug": {"type": "string"}, "document_type": {"type": "string"}, "title": {"type": "string"}, "html_template": {"type": "string"}, "style_id": {"type": "string", "description": "ID del estilo CSS, ej. pds-1"}, "variables": {"type": "string"}, "default_only": {"type": "boolean"}, "fields": {"type": "object", "description": "Opcional en update; también se aceptan html_template/style_id/variables en el nivel superior"}}, "required": ["action"]}},
    {"name": "pdf_style", "description": "CRUD de pdf_template_styles (CSS reutilizable, IDs pds-N). No edita HTML. action=list|get|create|update. create requiere slug, title, css_content. update requiere style_id y al menos un campo (style_guide, css_content, title, …) en el nivel superior o en fields. Escribir Markdown en el chat NO guarda style_guide.", "schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["list", "get", "create", "update"]}, "style_id": {"type": "string", "description": "ID prefijado, ej. pds-1"}, "slug": {"type": "string"}, "title": {"type": "string"}, "css_content": {"type": "string"}, "style_guide": {"type": "string", "description": "Markdown de clases/etiquetas. En update puede ir aquí (nivel superior) o en fields.style_guide"}, "description": {"type": "string"}, "fields": {"type": "object", "description": "Opcional en update; también se acepta style_guide/css_content en el nivel superior"}}, "required": ["action"]}},
    {"name": "generate_pdf", "description": "Genera PDF desde plantilla HTML (template_id) con variables. Preview de diseño, no a partir de un registro de carrera.", "schema": {"type": "object", "properties": {"template_id": {"type": "string", "description": "ID prefijado, ej. pdt-1"}, "variables": {"type": "object"}, "title": {"type": "string"}}, "required": ["template_id"]}},
    {"name": "list_pdf_capable_resources", "description": "Tablas que pueden emitir PDF (cv-versions, cover-letter-versions) y cómo mapear campos al template.", "schema": {"type": "object", "properties": {}}},
    {"name": "render_record_pdf", "description": "Genera el PDF de un registro con función PDF. resource_key + record_id; template_id opcional (si falta, plantilla default del document_type).", "schema": {"type": "object", "properties": {"resource_key": {"type": "string", "description": "cv-versions o cover-letter-versions"}, "record_id": _RECORD_ID_PARAM, "template_id": {"type": "string", "description": "Opcional, ej. pdt-1"}, "title": {"type": "string"}}, "required": ["resource_key", "record_id"]}},
    {
        "name": "generate_image",
        "description": (
            "Pide el prompt al solicitante y genera una imagen IA para agentes/proyectos/publicaciones. "
            "Ajusta y sube a MinIO en la carpeta de purpose ya en la medida exacta (500x500 agentes, "
            "1920x1080 proyectos/publicaciones), PNG comprimido para web. name opcional (si falta, se deriva del prompt)."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "purpose": {"type": "string", "enum": ["agentes", "proyectos", "publicaciones"]},
                "name": {"type": "string", "description": "Nombre legible para el archivo (opcional)"},
            },
            "required": ["prompt", "purpose"],
        },
    },
    {
        "name": "store_uploaded_image",
        "description": (
            "Cuando el solicitante YA tiene una imagen (adjunta en el chat, file_id) y solo quiere optimizarla "
            "y guardarla — sin generar nada nuevo. Ajusta a la medida exacta del purpose y sube a MinIO igual "
            "que generate_image, devolviendo el link."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "source_file_id": {"type": "string", "description": "file_id del adjunto ya subido"},
                "purpose": {"type": "string", "enum": ["agentes", "proyectos", "publicaciones"]},
                "name": {"type": "string", "description": "Nombre legible para el archivo (opcional)"},
            },
            "required": ["source_file_id", "purpose"],
        },
    },
    {
        "name": "attach_image_to_record",
        "description": "Pone image_url en publications, projects, o la foto de un agente del catálogo (resource_key=agent-profile, record_id=id del perfil).",
        "schema": {
            "type": "object",
            "properties": {
                "resource_key": {"type": "string", "enum": ["publications", "projects", "agent-profile"]},
                "record_id": _RECORD_ID_PARAM,
                "image_url": {"type": "string"},
            },
            "required": ["resource_key", "record_id", "image_url"],
        },
    },
    {
        "name": "list_generated_images",
        "description": "Lista imágenes generadas/guardadas por el agente Visual (agentes/proyectos/publicaciones). purpose opcional filtra una sola sección.",
        "schema": {
            "type": "object",
            "properties": {
                "purpose": {"type": "string", "enum": ["agentes", "proyectos", "publicaciones"]},
                "limit": {"type": "integer"},
            },
        },
    },
    {"name": "delegate_to_specialist", "description": "Delega a un especialista de nivel inferior (L1→L2|L3, L2→L3). Nunca hacia arriba.", "schema": {"type": "object", "properties": {"agent_profile_id": {"type": "string"}, "task": {"type": "string"}, "context": {"type": "string"}}, "required": ["agent_profile_id", "task"]}},
    {"name": "list_job_providers", "description": "Portales de vacantes habilitados (indeed, linkedin, getonboard, remotive, remoteok, company_boards).", "schema": {"type": "object", "properties": {}}},
    {
        "name": "run_job_discovery",
        "description": (
            "Busca vacantes y devuelve un PREVIEW con refs L1, L2… No crea registros. "
            "providers: indeed (vía Adzuna), linkedin (solo URLs oficiales de búsqueda; no inventes vacantes), "
            "getonboard, remotive, remoteok. Presenta la lista a Carlos y ESPERA a que autorice refs concretas "
            "antes de save_job_listings."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "location": {"type": "string"},
                "providers": {"type": "array", "items": {"type": "string"}},
                "target_role_id": {"type": "string", "description": "ID prefijado del rol objetivo, ej. trl-2"},
                "include_company_boards": {"type": "boolean"},
                "remote": {"type": "boolean"},
            },
        },
    },
    {
        "name": "import_job_url",
        "description": (
            "Importa UNA vacante concreta por URL (linkedin.com/jobs/view/..., Indeed, OCC) al preview "
            "con una ref nueva. Si Carlos pegó la URL, eso autoriza guardar esa ref."
        ),
        "schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "save_job_listings",
        "description": (
            "Crea vacancies con evaluation=pending_review SOLO de refs (L1, L3…) que Carlos autorizó "
            "de la última búsqueda o import. Prohibido llamar sin autorización explícita. "
            "No inventes refs ni pases listings inventados. Omite search_url."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Refs autorizadas, p.ej. ['L1','L3']",
                },
                "target_role_id": {"type": "string", "description": "ID prefijado del rol objetivo, ej. trl-2"},
            },
            "required": ["refs"],
        },
    },
    {"name": "web_search", "description": "Busca en internet. Devuelve títulos, URLs y snippets. No inventes fuentes.", "schema": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]}},
    {"name": "web_fetch", "description": "Lee el texto de una URL http/https pública. Bloquea redes privadas. No uses URLs inventadas.", "schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "get_github_status", "description": "Estado de la conexión GitHub (GITHUB_TOKEN).", "schema": {"type": "object", "properties": {}}},
    {"name": "list_github_repos", "description": "Lista repos del usuario autenticado o de un owner. query filtra por nombre/descripcion.", "schema": {"type": "object", "properties": {"owner": {"type": "string"}, "query": {"type": "string"}, "per_page": {"type": "integer"}}}},
    {"name": "get_github_repo", "description": "Metadatos de un repo. owner opcional; repo acepta 'owner/name'.", "schema": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["repo"]}},
    {"name": "list_github_contents", "description": "Lista archivos/carpetas de un repo. path vacío = raíz.", "schema": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "ref": {"type": "string"}}, "required": ["repo"]}},
    {"name": "get_github_file", "description": "Lee el contenido de un archivo de un repo (texto, truncado).", "schema": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "ref": {"type": "string"}}, "required": ["repo", "path"]}},
    {"name": "search_github_code", "description": "Busca código en repos del usuario. Requiere GITHUB_TOKEN.", "schema": {"type": "object", "properties": {"query": {"type": "string"}, "owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["query"]}},
    {
        "name": "agent_catalog_settings",
        "description": "Catálogo de agentes: prompt suffix, destinos de delegación y metodologías asignadas por perfil. action=list|get|update_prompt|update_delegation|update_methodologies. profile_id requerido salvo list.",
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "get", "update_prompt", "update_delegation", "update_methodologies"]},
                "profile_id": {"type": "string", "description": "Nombre de sistema (agent_professional_identity) o record id (agent-2)"},
                "system_prompt_suffix": {"type": "string", "description": "update_prompt: null/omitido restaura el default del código"},
                "target_ids": {"type": "array", "items": {"type": "string"}, "description": "update_delegation: destinos permitidos; [] = no delega a nadie; omitido restaura el default por nivel"},
                "methodology_ids": {"type": "array", "items": {"type": "string"}, "description": "update_methodologies: IDs opm-N que este agente debe consultar"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "admin_section_settings",
        "description": (
            "Secciones del Admin: qué agente L2 atiende el chat contextual de cada "
            "pantalla. action=list|get|update. section_id es el PK sec-N (p.ej. sec-1); "
            "mira action=list, campo id. El campo system_name (dashboard, career-projects…) "
            "es solo el nombre legible. section_id requerido salvo en list."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "get", "update"]},
                "section_id": {"type": "string", "description": "PK de la sección, p.ej. sec-1 (NO el system_name)"},
                "agent_profile_id": {"type": "string", "description": "Agente L2 del chat contextual del sidebar; string vacío restaura el default del código; debe ser un agente de nivel 2"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "bedrock_global_settings",
        "description": "Prompts globales que aplican a TODOS los agentes (system prompt base + reglas de grounding/metodologías). action=get|update_system_prompt|update_global_rules.",
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "update_system_prompt", "update_global_rules"]},
                "text": {"type": "string", "description": "null/omitido restaura el default del código"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "error_report_settings",
        "description": "Reportes de falla del sistema (tabla error_reports, IDs err-N). action=list|get|resolve|reopen|summary. list acepta resolved(bool), severity(warning|error|critical), limit. get/resolve/reopen requieren report_id. resolve acepta resolution_notes. Marcar resuelto = el problema ya se corrigió en el sistema.",
        "schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "get", "resolve", "reopen", "summary"]},
                "report_id": {"type": "string", "description": "ID prefijado, ej. err-3"},
                "resolved": {"type": "boolean", "description": "list: filtra por estado (false = pendientes)"},
                "severity": {"type": "string", "enum": ["warning", "error", "critical"]},
                "limit": {"type": "integer"},
                "resolution_notes": {"type": "string", "description": "resolve: qué se hizo para resolver"},
            },
            "required": ["action"],
        },
    },
]

_WRITE_TOOLS = {
    "create_career_record",
    "update_career_record",
    "bulk_update_career_record",
    "delete_career_record",
    "create_linkedin_post",
    "pdf_template",
    "pdf_style",
    "generate_pdf",
    "render_record_pdf",
    "generate_image",
    "store_uploaded_image",
    "attach_image_to_record",
    "save_job_listings",
    "agent_catalog_settings",
    "admin_section_settings",
    "bedrock_global_settings",
    "error_report_settings",
}

_PDF_TEMPLATE_ALIASES = {
    "list_pdf_templates": "list",
    "get_pdf_template": "get",
    "create_pdf_template": "create",
    "update_pdf_template": "update",
}

_PDF_STYLE_ALIASES = {
    "list_pdf_template_styles": "list",
    "get_pdf_template_style": "get",
    "create_pdf_template_style": "create",
    "update_pdf_template_style": "update",
}

_PDF_TEMPLATE_UPDATE_FIELDS = {
    "slug",
    "document_type",
    "title",
    "description",
    "html_template",
    "style_id",
    "variables",
    "variables_schema",
    "preview_notes",
    "is_active",
    "is_default",
}

# Tablas de carrera con función PDF (L3 agent_pdf_render).
PDF_CAPABLE_RESOURCES = {
    "cv-versions": {
        "document_type": "cv",
        "content_attr": "content",
        "title_attr": "title",
    },
    "cover-letter-versions": {
        "document_type": "cover_letter",
        "content_attr": "body_content",
        "title_attr": "title",
    },
}

_LEGACY = {
    "list_recent_changes", "restore_deleted_record", "describe_resource_schema", "search_knowledge_base",
    "list_career_record", "count_career_records", "get_career_record", "create_career_record", "update_career_record", "delete_career_record",
}


# ============================================================================
# Especificaciones Converse
# ============================================================================

def all_tool_names() -> Set[str]:
    return {t["name"] for t in _RAW_TOOLS}


def converse_tool_specs(
    allowed: Optional[Set[str]] = None,
    *,
    caller_profile=None,
    delegate_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Convierte definiciones a formato toolConfig.tools de Converse API."""
    specs = []
    for t in _RAW_TOOLS:
        if allowed is not None and t["name"] not in allowed:
            continue
        description = t["description"]
        if t["name"] == "delegate_to_specialist" and caller_profile is not None:
            from services.bedrock.agent_profiles import delegate_tool_description
            description = delegate_tool_description(caller_profile, target_ids=delegate_ids)
        if t["name"] == "search_knowledge_base" and caller_profile is not None:
            from services.bedrock.agent_profiles import AGENT_METHODOLOGIES
            if caller_profile.id == AGENT_METHODOLOGIES:
                description = (
                    "Búsqueda semántica Qdrant. Con type=methodology ves TODAS las metodologías "
                    "(eres el guardián). NO usar para 'lista todos mis X' — usa list_career_record."
                )
            else:
                description = (
                    f"Búsqueda semántica Qdrant. Con type=methodology SOLO devuelve metodologías "
                    f"asignadas a {caller_profile.id} (agent_profile_ids) o compartidas (lista vacía). "
                    "NO usar para 'lista todos mis X' — usa list_career_record."
                )
        specs.append({
            "toolSpec": {
                "name": t["name"],
                "description": description,
                "inputSchema": {"json": t["schema"]},
            }
        })
    return specs


# ============================================================================
# Tools de integración
# ============================================================================

async def _linkedin_connection(db, user_id: str) -> Optional[LinkedInConnection]:
    result = await db.execute(select(LinkedInConnection).where(LinkedInConnection.user_id == user_id))
    conn = result.scalar_one_or_none()
    if conn and conn.expires_at > datetime.now(timezone.utc):
        return conn
    return None


async def _run_pdf_template(db, user_id: str, action: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """CRUD de pdf_output_templates (HTML)."""
    if action == "list":
        q = select(PdfOutputTemplate).where(PdfOutputTemplate.user_id == user_id, PdfOutputTemplate.is_active.is_(True))
        if tool_input.get("document_type"):
            q = q.where(PdfOutputTemplate.document_type == tool_input["document_type"])
        result = await db.execute(q.order_by(PdfOutputTemplate.title))
        rows = result.scalars().all()
        return {
            "items": [
                {
                    "id": r.id,
                    "slug": r.slug,
                    "document_type": r.document_type,
                    "title": r.title,
                    "style_id": r.style_id,
                    "is_default": r.is_default,
                }
                for r in rows
            ]
        }

    if action == "get":
        q = select(PdfOutputTemplate).where(PdfOutputTemplate.user_id == user_id, PdfOutputTemplate.is_active.is_(True))
        if tool_input.get("template_id"):
            template_id = normalize_prefixed_id("pdf_output_templates", tool_input["template_id"])
            q = q.where(PdfOutputTemplate.id == template_id)
        elif tool_input.get("slug"):
            q = q.where(PdfOutputTemplate.slug == tool_input["slug"])
        elif tool_input.get("default_only") and tool_input.get("document_type"):
            q = q.where(
                PdfOutputTemplate.document_type == tool_input["document_type"],
                PdfOutputTemplate.is_default.is_(True),
            )
        else:
            return {"error": "specify template_id, slug, or default_only+document_type"}
        result = await db.execute(q.limit(1))
        row = result.scalar_one_or_none()
        if not row:
            return {"error": "not_found"}
        return {
            "item": {
                "id": row.id,
                "slug": row.slug,
                "html_template": row.html_template[:2000],
                "style_id": row.style_id,
                "variables": row.variables,
                "variables_schema": row.variables_schema,
            }
        }

    if action == "create":
        missing = [k for k in ("slug", "document_type", "title", "html_template") if not tool_input.get(k)]
        if missing:
            return {"error": f"create requires {', '.join(missing)}"}
        row = PdfOutputTemplate(
            user_id=user_id,
            slug=tool_input["slug"],
            document_type=tool_input["document_type"],
            title=tool_input["title"],
            html_template=tool_input["html_template"],
            style_id=normalize_prefixed_id("pdf_template_styles", tool_input["style_id"])
            if tool_input.get("style_id")
            else None,
            variables=tool_input.get("variables"),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return {"item": {"id": row.id, "slug": row.slug}}

    if action == "update":
        if not tool_input.get("template_id"):
            return {"error": "update requires template_id"}
        template_id = normalize_prefixed_id("pdf_output_templates", tool_input["template_id"])
        result = await db.execute(
            select(PdfOutputTemplate).where(PdfOutputTemplate.id == template_id, PdfOutputTemplate.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            return {"error": "not_found"}
        fields = merge_writable_fields(tool_input, _PDF_TEMPLATE_UPDATE_FIELDS)
        if fields.get("style_id"):
            fields["style_id"] = normalize_prefixed_id("pdf_template_styles", fields["style_id"])
        if not fields:
            return {"error": "update requires html_template, style_id, variables, title, slug, document_type, is_default, or is_active"}
        for key, value in fields.items():
            setattr(row, key, value)
        row.version = (row.version or 1) + 1
        await db.commit()
        return {"item": {"id": row.id, "version": row.version, "updated_fields": sorted(fields.keys())}}

    return {"error": f"unknown action: {action}"}


async def _run_pdf_style(db, user_id: str, action: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """CRUD de pdf_template_styles (CSS)."""
    if action == "list":
        result = await db.execute(
            select(PdfTemplateStyle)
            .where(PdfTemplateStyle.user_id == user_id, PdfTemplateStyle.is_active.is_(True))
            .order_by(PdfTemplateStyle.title)
        )
        rows = result.scalars().all()
        return {
            "items": [
                {"id": r.id, "slug": r.slug, "title": r.title, "description": r.description}
                for r in rows
            ]
        }

    if action == "get":
        q = select(PdfTemplateStyle).where(PdfTemplateStyle.user_id == user_id, PdfTemplateStyle.is_active.is_(True))
        if tool_input.get("style_id"):
            style_id = normalize_prefixed_id("pdf_template_styles", tool_input["style_id"])
            q = q.where(PdfTemplateStyle.id == style_id)
        elif tool_input.get("slug"):
            q = q.where(PdfTemplateStyle.slug == tool_input["slug"])
        else:
            return {"error": "specify style_id or slug"}
        result = await db.execute(q.limit(1))
        row = result.scalar_one_or_none()
        if not row:
            return {"error": "not_found"}
        return {
            "item": {
                "id": row.id,
                "slug": row.slug,
                "title": row.title,
                "description": row.description,
                "css_content": row.css_content,
                "style_guide": row.style_guide,
                "is_active": row.is_active,
            }
        }

    if action == "create":
        missing = [k for k in ("slug", "title", "css_content") if not tool_input.get(k)]
        if missing:
            return {"error": f"create requires {', '.join(missing)}"}
        row = await _PDF_STYLE_REPO.create_for_user(
            db,
            user_id,
            {
                "slug": tool_input["slug"],
                "title": tool_input["title"],
                "css_content": tool_input["css_content"],
                "style_guide": tool_input.get("style_guide"),
                "description": tool_input.get("description"),
            },
        )
        return {"item": {"id": row.id, "slug": row.slug}}

    if action == "update":
        if not tool_input.get("style_id"):
            return {"error": "update requires style_id"}
        style_id = normalize_prefixed_id("pdf_template_styles", tool_input["style_id"])
        fields = merge_writable_fields(tool_input, _PDF_STYLE_UPDATE_FIELDS)
        if not fields:
            return {"error": "update requires style_guide, css_content, title, slug, description, or is_active"}
        row = await _PDF_STYLE_REPO.update_for_user(db, user_id, style_id, fields)
        if not row:
            return {"error": "not_found"}
        payload: Dict[str, Any] = {
            "id": row.id,
            "slug": row.slug,
            "updated_fields": sorted(fields.keys()),
        }
        if "style_guide" in fields:
            payload["style_guide_chars"] = len(row.style_guide or "")
        return {"item": payload}

    return {"error": f"unknown action: {action}"}


async def _load_pdf_template(db, user_id: str, template_id: str) -> Optional[PdfOutputTemplate]:
    template_id = normalize_prefixed_id("pdf_output_templates", template_id)
    result = await db.execute(
        select(PdfOutputTemplate).where(
            PdfOutputTemplate.id == template_id,
            PdfOutputTemplate.user_id == user_id,
            PdfOutputTemplate.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def _default_pdf_template(db, user_id: str, document_type: str) -> Optional[PdfOutputTemplate]:
    result = await db.execute(
        select(PdfOutputTemplate).where(
            PdfOutputTemplate.user_id == user_id,
            PdfOutputTemplate.document_type == document_type,
            PdfOutputTemplate.is_default.is_(True),
            PdfOutputTemplate.is_active.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    if row:
        return row
    fallback = await db.execute(
        select(PdfOutputTemplate)
        .where(
            PdfOutputTemplate.user_id == user_id,
            PdfOutputTemplate.document_type == document_type,
            PdfOutputTemplate.is_active.is_(True),
        )
        .order_by(PdfOutputTemplate.title)
        .limit(1)
    )
    return fallback.scalar_one_or_none()


def _store_generated_pdf(pdf_bytes: bytes, slug: str, title: str, template_id: str) -> Dict[str, Any]:
    stored = storage_service.upload_file(
        data=io.BytesIO(pdf_bytes),
        original_filename=f"{slug}.pdf",
        size=len(pdf_bytes),
        content_type="application/pdf",
        category="pdf-generated",
        is_public=True,
    )
    url = storage_service.get_public_url(stored)
    return {"pdf_url": url, "filename": stored, "template_id": template_id, "title": title}


async def _render_template_to_pdf(db, row: PdfOutputTemplate, variables: Dict[str, Any], title: str) -> Dict[str, Any]:
    from services.pdf_service import generate_html_template_pdf
    from services.pdf_template_css import resolve_template_css
    from services.pdf_template_render import render_template_html

    html = render_template_html(row.html_template, variables)
    css_content = await resolve_template_css(db, row)
    pdf_bytes = await generate_html_template_pdf(title=title, html_body=html, css_content=css_content)
    return _store_generated_pdf(pdf_bytes, row.slug, title, row.id)


async def _run_generate_pdf(db, user_id: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    row = await _load_pdf_template(db, user_id, tool_input["template_id"])
    if not row:
        return {"error": "not_found"}
    variables = tool_input.get("variables") or {}
    title = tool_input.get("title") or row.title
    return await _render_template_to_pdf(db, row, variables, title)


async def _run_render_record_pdf(db, user_id: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    resource_key = tool_input.get("resource_key") or ""
    meta = PDF_CAPABLE_RESOURCES.get(resource_key)
    if not meta:
        return {
            "error": "resource_not_pdf_capable",
            "allowed": sorted(PDF_CAPABLE_RESOURCES.keys()),
        }
    record_id = tool_input.get("record_id")
    if not record_id:
        return {"error": "record_id required"}
    repo = bedrock_service._get_repository(resource_key)
    record = await repo.get_for_user(db, user_id, record_id)
    if record is None:
        return {"error": "not_found"}
    content = getattr(record, meta["content_attr"], None) or ""
    if not str(content).strip():
        return {"error": "record_has_no_content"}
    title = tool_input.get("title") or getattr(record, meta["title_attr"], None) or resource_key
    if tool_input.get("template_id"):
        row = await _load_pdf_template(db, user_id, tool_input["template_id"])
    else:
        row = await _default_pdf_template(db, user_id, meta["document_type"])
    if not row:
        return {
            "error": "no_template",
            "document_type": meta["document_type"],
            "hint": "Crea una plantilla default con agent_pdf_design o pasa template_id.",
        }
    variables = {"title": title, "content": content, "body": content}
    result = await _render_template_to_pdf(db, row, variables, title)
    result["resource_key"] = resource_key
    result["record_id"] = record.id
    return result


async def _run_agent_catalog_settings(db, user_id: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Catálogo de agentes (L2 agent_configuration): prompt, delegación, metodologías."""
    from services.bedrock import profile_catalog, profile_delegation, profile_prompts
    from services.bedrock.agent_profiles import get_profile
    from services.methodology_scope import set_agent_methodologies

    action = tool_input.get("action")

    if action == "list":
        return {"items": await profile_catalog.list_catalog(db, user_id)}

    profile_id = tool_input.get("profile_id")
    if not profile_id:
        return {"error": "profile_id is required for this action"}
    try:
        get_profile(profile_id)
    except KeyError:
        return {"error": f"unknown agent profile: {profile_id}"}

    if action == "get":
        return {"item": await profile_catalog.get_catalog_item(db, user_id, profile_id)}

    if action == "update_prompt":
        item = await profile_prompts.set_profile_prompt_suffix(
            db, profile_id, tool_input.get("system_prompt_suffix")
        )
        return {"item": item}

    if action == "update_delegation":
        target_ids = tool_input.get("target_ids")
        item = await profile_delegation.set_delegation_targets(db, profile_id, target_ids)
        return {"item": item}

    if action == "update_methodologies":
        methodology_ids = tool_input.get("methodology_ids") or []
        items = await set_agent_methodologies(db, user_id, profile_id, methodology_ids)
        return {"items": items}

    return {"error": f"unknown action: {action}"}


async def _run_admin_section_settings(db, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Secciones del Admin (L2 agent_configuration): agente L2 del chat contextual."""
    from services import section_catalog
    from services.admin_sections import get_section_spec, is_l2
    from services.bedrock.agent_profiles import get_profile

    action = tool_input.get("action")

    if action == "list":
        return {"items": await section_catalog.list_sections(db)}

    section_id = tool_input.get("section_id")
    if not section_id:
        return {"error": "section_id (PK sec-N) is required for this action"}
    try:
        get_section_spec(section_id)
    except KeyError:
        return {
            "error": (
                f"unknown admin section: {section_id!r}. section_id debe ser el PK sec-N "
                "(usa action=list y toma el campo 'id'; 'system_name' es solo el nombre legible)"
            )
        }

    if action == "get":
        return {"item": await section_catalog.get_section(db, section_id)}

    if action == "update":
        agent_id = tool_input.get("agent_profile_id")
        clear_agent = False
        if agent_id is not None:
            if agent_id == "":
                clear_agent = True
                agent_id = None
            else:
                try:
                    get_profile(agent_id)
                except KeyError:
                    return {"error": f"unknown agent profile: {agent_id}"}
                if not is_l2(agent_id):
                    return {"error": f"agent profile is not L2: {agent_id}"}
        try:
            item = await section_catalog.update_section(
                db,
                section_id,
                agent_profile_id=agent_id,
                clear_agent=clear_agent,
            )
        except (KeyError, ValueError) as exc:
            return {"error": str(exc)}
        return {"item": item}

    return {"error": f"unknown action: {action}"}


async def _run_bedrock_global_settings(db, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Prompts globales (L2 agent_configuration): aplican a TODOS los agentes."""
    action = tool_input.get("action")

    async def _snapshot() -> Dict[str, Any]:
        prompt = await bedrock_service.get_system_prompt(db)
        rules = await bedrock_service.get_global_rules(db)
        return {
            "system_prompt": prompt,
            "system_prompt_is_default": prompt == bedrock_service.default_system_prompt(),
            "global_rules": rules,
            "global_rules_is_default": rules == bedrock_service.default_global_rules(),
        }

    if action == "get":
        return await _snapshot()

    if action == "update_system_prompt":
        text = tool_input.get("text")
        await bedrock_service.set_system_prompt(db, text.strip() if text else None)
        return await _snapshot()

    if action == "update_global_rules":
        text = tool_input.get("text")
        await bedrock_service.set_global_rules(db, text.strip() if text else None)
        return await _snapshot()

    return {"error": f"unknown action: {action}"}


async def _run_error_report_settings(db, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Reportes de falla del sistema (L2 agent_settings): consulta y resolución."""
    from services import error_report_service

    action = tool_input.get("action")

    if action == "summary":
        return await error_report_service.summary(db)

    if action == "list":
        limit = min(int(tool_input.get("limit") or 20), 100)
        return await error_report_service.list_reports(
            db,
            resolved=tool_input.get("resolved"),
            severity=tool_input.get("severity"),
            page=1,
            page_size=limit,
        )

    report_id = tool_input.get("report_id")
    if not report_id:
        return {"error": "report_id is required for this action"}

    if action == "get":
        item = await error_report_service.get_report(db, report_id)
        return {"item": item} if item else {"error": f"unknown error report: {report_id}"}

    if action == "resolve":
        item = await error_report_service.resolve_report(
            db,
            report_id,
            notes=tool_input.get("resolution_notes"),
            actor="agent_settings",
        )
        return {"item": item} if item else {"error": f"unknown error report: {report_id}"}

    if action == "reopen":
        item = await error_report_service.reopen_report(db, report_id, actor="agent_settings")
        return {"item": item} if item else {"error": f"unknown error report: {report_id}"}

    return {"error": f"unknown action: {action}"}


async def _execute_extended(db, user_id: str, name: str, tool_input: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    """Tools nuevos del harness local (no en monolito legacy)."""
    if name == "bulk_update_career_record":
        resource_key = tool_input.get("resource_key")
        updates = tool_input.get("updates") or []
        if not resource_key:
            return {"error": "falta resource_key"}
        if not updates:
            return {"error": "updates vacío: pasa al menos un {record_id, fields}"}
        if len(updates) > 200:
            return {"error": f"updates trae {len(updates)} items; máximo 200 por llamada"}
        updated_ids: List[str] = []
        errors: List[Dict[str, Any]] = []
        for entry in updates:
            record_id = entry.get("record_id") if isinstance(entry, dict) else None
            fields = entry.get("fields") if isinstance(entry, dict) else None
            if not record_id or not isinstance(fields, dict):
                errors.append({"record_id": record_id, "error": "falta record_id o fields"})
                continue
            try:
                result = await bedrock_service._execute_tool(
                    db, user_id, "update_career_record",
                    {"resource_key": resource_key, "record_id": record_id, "fields": fields},
                    session_id,
                )
            except Exception as e:
                # Un fallo de flush (p.ej. constraint) deja la sesión en
                # pending-rollback: sin este rollback, todo item restante del
                # lote fallaría con un error genérico que oculta cuál fue el
                # que realmente rompió.
                await db.rollback()
                errors.append({"record_id": record_id, "error": str(e)})
                continue
            if isinstance(result, dict) and result.get("error"):
                errors.append({"record_id": record_id, "error": result["error"]})
            else:
                updated_ids.append(record_id)
        return {
            "resource_key": resource_key,
            "updated_count": len(updated_ids),
            "updated_ids": updated_ids,
            "error_count": len(errors),
            "errors": errors,
        }

    if name == "get_linkedin_status":
        conn = await _linkedin_connection(db, user_id)
        if not conn:
            return {"connected": False}
        return {"connected": True, "member_name": conn.member_name, "expires_at": str(conn.expires_at)}

    if name == "list_linkedin_posts":
        limit = min(tool_input.get("limit", 20), 50)
        result = await db.execute(
            select(LinkedInPost).where(LinkedInPost.user_id == user_id).order_by(desc(LinkedInPost.created_at)).limit(limit)
        )
        posts = result.scalars().all()
        return {
            "items": [
                {"id": p.id, "text": p.text[:200], "status": p.status, "scheduled_at": str(p.scheduled_at) if p.scheduled_at else None}
                for p in posts
            ]
        }

    if name == "create_linkedin_post":
        from services import linkedin_service

        conn = await _linkedin_connection(db, user_id)
        if not conn:
            return {"error": "LinkedIn not connected"}
        text = tool_input["text"]
        scheduled_at = tool_input.get("scheduled_at")
        image_url = tool_input.get("image_url")
        image_bytes = None
        if image_url:
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(image_url)
                r.raise_for_status()
                image_bytes = r.content

        scheduled_dt = None
        if scheduled_at:
            scheduled_dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            if scheduled_dt.tzinfo is None:
                scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)

        if scheduled_dt and scheduled_dt > datetime.now(timezone.utc):
            post = LinkedInPost(user_id=user_id, text=text, image_url=image_url, status=LinkedInPostStatus.SCHEDULED, scheduled_at=scheduled_dt)
            db.add(post)
            await db.commit()
            await db.refresh(post)
            return {"scheduled": True, "post_id": post.id, "scheduled_at": str(scheduled_dt)}

        try:
            image_urn = None
            if image_bytes:
                image_urn = await linkedin_service.upload_image(conn.access_token, conn.member_sub, image_bytes)
            post_urn = await linkedin_service.create_post(conn.access_token, conn.member_sub, text, image_urn)
        except Exception as e:
            return {"error": str(e)}
        post = LinkedInPost(
            user_id=user_id, text=text, image_url=image_url, status=LinkedInPostStatus.PUBLISHED,
            linkedin_post_urn=post_urn, published_at=datetime.now(timezone.utc),
        )
        db.add(post)
        await db.commit()
        return {"published": True, "linkedin_post_urn": post_urn}

    if name == "delete_scheduled_linkedin_post":
        post_id = normalize_prefixed_id("linkedin_posts", tool_input["post_id"])
        result = await db.execute(select(LinkedInPost).where(LinkedInPost.id == post_id, LinkedInPost.user_id == user_id))
        post = result.scalar_one_or_none()
        if not post:
            return {"error": "not_found"}
        if post.status != LinkedInPostStatus.SCHEDULED:
            return {"error": "only_scheduled_can_be_deleted"}
        await db.delete(post)
        await db.commit()
        return {"deleted": True}

    if name == "pdf_template" or name in _PDF_TEMPLATE_ALIASES:
        action = tool_input.get("action") or _PDF_TEMPLATE_ALIASES.get(name)
        return await _run_pdf_template(db, user_id, action, tool_input)

    if name == "pdf_style" or name in _PDF_STYLE_ALIASES:
        action = tool_input.get("action") or _PDF_STYLE_ALIASES.get(name)
        return await _run_pdf_style(db, user_id, action, tool_input)

    if name == "list_pdf_capable_resources":
        return {
            "resources": [
                {"resource_key": key, **meta}
                for key, meta in PDF_CAPABLE_RESOURCES.items()
            ]
        }

    if name == "generate_pdf":
        return await _run_generate_pdf(db, user_id, tool_input)

    if name == "render_record_pdf":
        return await _run_render_record_pdf(db, user_id, tool_input)

    if name == "agent_catalog_settings":
        return await _run_agent_catalog_settings(db, user_id, tool_input)

    if name == "admin_section_settings":
        return await _run_admin_section_settings(db, tool_input)

    if name == "bedrock_global_settings":
        return await _run_bedrock_global_settings(db, tool_input)

    if name == "error_report_settings":
        return await _run_error_report_settings(db, tool_input)

    if name == "generate_image":
        from models.file_upload import FileType, FileUpload
        from services.bedrock import image_pipeline
        from services.bedrock.image_client import generate_image_bytes

        spec = image_pipeline.resolve_purpose(tool_input["purpose"])
        prompt = (tool_input.get("prompt") or "").strip()
        if not prompt:
            raise BedrockError("prompt vacío: describe qué imagen generar")
        aspect_ratio = image_pipeline.stability_aspect_ratio(spec)
        raw = await generate_image_bytes(prompt, aspect_ratio=aspect_ratio)
        finalized = image_pipeline.finalize_png(raw, spec)
        name_hint = image_pipeline.slug_name(tool_input.get("name"), prompt)
        stored = storage_service.upload_file(
            data=io.BytesIO(finalized), original_filename=f"{name_hint}.png", size=len(finalized),
            content_type="image/png", category=spec.category, is_public=True, name_hint=name_hint,
        )
        url = storage_service.get_public_url(stored)
        row = FileUpload(
            user_id=user_id, original_filename=f"{name_hint}.png", stored_filename=stored, file_path=stored,
            file_type=FileType.IMAGE, mime_type="image/png", file_size=len(finalized),
            description=prompt[:500], category=spec.category, is_public=True,
            download_url=url,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        await db.commit()
        return {"image_url": url, "filename": stored, "purpose": spec.category}

    if name == "store_uploaded_image":
        from models.file_upload import FileType, FileUpload
        from services.bedrock import image_pipeline

        spec = image_pipeline.resolve_purpose(tool_input["purpose"])
        result = await db.execute(
            select(FileUpload).where(
                FileUpload.id == tool_input["source_file_id"],
                FileUpload.user_id == user_id,
                FileUpload.is_active.is_(True),
            )
        )
        source = result.scalar_one_or_none()
        if source is None:
            return {"error": f"Adjunto no encontrado: {tool_input['source_file_id']}"}
        if not (source.mime_type or "").startswith("image/"):
            return {"error": "El archivo de origen no es una imagen"}

        response = storage_service.get_object_stream(source.stored_filename)
        try:
            raw = response.read()
        finally:
            response.close()
            response.release_conn()

        finalized = image_pipeline.finalize_png(raw, spec)
        name_hint = image_pipeline.slug_name(tool_input.get("name"), source.original_filename)
        stored = storage_service.upload_file(
            data=io.BytesIO(finalized), original_filename=f"{name_hint}.png", size=len(finalized),
            content_type="image/png", category=spec.category, is_public=True, name_hint=name_hint,
        )
        url = storage_service.get_public_url(stored)
        row = FileUpload(
            user_id=user_id, original_filename=f"{name_hint}.png", stored_filename=stored, file_path=stored,
            file_type=FileType.IMAGE, mime_type="image/png", file_size=len(finalized),
            description=f"Optimizada desde {source.original_filename}", category=spec.category, is_public=True,
            download_url=url,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        await db.commit()
        return {"image_url": url, "filename": stored, "purpose": spec.category}

    if name == "attach_image_to_record":
        rk = tool_input["resource_key"]
        if rk == "agent-profile":
            from services.bedrock import profile_photos

            return await profile_photos.set_photo(db, tool_input["record_id"], tool_input["image_url"])
        if rk not in ("publications", "projects"):
            return {"error": "resource_key must be publications, projects, or agent-profile"}
        return await bedrock_service._execute_tool(
            db, user_id, "update_career_record",
            {
                "resource_key": rk,
                "record_id": normalize_prefixed_id(rk, tool_input["record_id"]),
                "fields": {"image_url": tool_input["image_url"]},
            },
            session_id,
        )

    if name == "list_generated_images":
        from models.file_upload import FileUpload
        from services.bedrock.image_pipeline import IMAGE_PURPOSES

        purpose = tool_input.get("purpose")
        categories = [IMAGE_PURPOSES[purpose].category] if purpose in IMAGE_PURPOSES else [
            spec.category for spec in IMAGE_PURPOSES.values()
        ]
        limit = min(tool_input.get("limit", 20), 50)
        result = await db.execute(
            select(FileUpload).where(FileUpload.user_id == user_id, FileUpload.category.in_(categories))
            .order_by(desc(FileUpload.created_at)).limit(limit)
        )
        files = result.scalars().all()
        return {"items": [{"filename": f.stored_filename, "url": f.download_url, "description": f.description, "purpose": f.category} for f in files]}

    if name == "delegate_to_specialist":
        return {"error": "delegate_to_specialist must be handled by agent_loop"}

    if name == "list_job_providers":
        from services.job_discovery import providers as list_job_providers

        return {
            "providers": [
                {
                    "id": p.id,
                    "label": p.label,
                    "enabled": p.enabled,
                    "reason": p.reason,
                    "listing_kind": p.listing_kind,
                }
                for p in list_job_providers()
            ]
        }

    if name == "run_job_discovery":
        from services.job_discovery import listing_to_dict, run_discovery

        try:
            result = await run_discovery(
                db,
                user_id,
                query_text=tool_input.get("query"),
                location=tool_input.get("location"),
                providers=tool_input.get("providers"),
                target_role_id=normalize_prefixed_id("target_roles", tool_input["target_role_id"])
                if tool_input.get("target_role_id") is not None
                else None,
                include_company_boards=bool(tool_input.get("include_company_boards")),
                remote=bool(tool_input.get("remote")),
                session_key=session_id,
            )
        except ValueError as exc:
            return {"error": str(exc)}
        return {
            "query": result.query,
            "location": result.location,
            "listings": [listing_to_dict(item) for item in result.listings],
            "errors": [{"provider": e.provider, "message": e.message} for e in result.errors],
            "instruction": (
                "Presenta a Carlos cada listing_kind=job con su ref (L1, L2…). "
                "No llames save_job_listings hasta que autorice refs concretas."
            ),
        }

    if name == "import_job_url":
        from services.job_discovery import import_vacancy_url, listing_to_dict
        from services.job_discovery.preview_store import append_preview

        listing = await import_vacancy_url(tool_input["url"])
        remembered = append_preview(user_id, session_id, listing_to_dict(listing))
        listing.ref = remembered["ref"]
        return listing_to_dict(listing)

    if name == "save_job_listings":
        from services.job_discovery import save_listings
        from services.job_discovery.preview_store import resolve_refs

        refs = tool_input.get("refs") or []
        if not refs:
            return {
                "error": (
                    "Faltan refs autorizadas. Espera a que Carlos elija L1, L3… "
                    "de la última búsqueda. No inventes vacantes."
                )
            }
        found, missing, available = resolve_refs(user_id, session_id, refs)
        if missing:
            return {
                "error": f"Refs no están en la última búsqueda: {missing}.",
                "available_refs": available,
            }
        if not found:
            return {"error": "No hay listings autorizados para guardar.", "available_refs": available}
        return await save_listings(
            db,
            user_id,
            found,
            target_role_id=normalize_prefixed_id("target_roles", tool_input["target_role_id"])
            if tool_input.get("target_role_id") is not None
            else None,
        )

    if name == "web_search":
        from services import web_search_service

        return await web_search_service.search(
            tool_input.get("query") or "",
            max_results=tool_input.get("max_results") or 8,
        )

    if name == "web_fetch":
        from services import web_search_service
        from services.web_search_service import WebSearchError

        try:
            return await web_search_service.fetch(tool_input.get("url") or "")
        except WebSearchError as exc:
            return {"error": str(exc)}

    if name == "get_github_status":
        from services import github_service

        return await github_service.connection_status()

    if name == "list_github_repos":
        from services import github_service

        return await github_service.list_repos(
            db,
            user_id,
            owner=tool_input.get("owner"),
            query=tool_input.get("query"),
            per_page=tool_input.get("per_page") or 30,
        )

    if name in ("get_github_repo", "list_github_contents", "get_github_file", "search_github_code"):
        from services import github_service

        repo = tool_input.get("repo") or ""
        owner = (tool_input.get("owner") or "").strip()
        if not owner and "/" not in repo:
            resolved = await github_service.resolve_owner(db, user_id, None)
            if resolved.get("error"):
                if name != "search_github_code":
                    return resolved
            else:
                owner = resolved["owner"]
        if name == "get_github_repo":
            return await github_service.get_repo(owner, repo)
        if name == "list_github_contents":
            return await github_service.list_contents(
                owner, repo, path=tool_input.get("path") or "", ref=tool_input.get("ref")
            )
        if name == "get_github_file":
            return await github_service.get_file(
                owner, repo, tool_input.get("path") or "", ref=tool_input.get("ref")
            )
        return await github_service.search_code(
            tool_input.get("query") or "", owner=owner or None, repo=repo or None
        )

    raise BedrockError(f"Unknown extended tool: {name}")


# ============================================================================
# Dispatch de tools
# ============================================================================

async def execute_tool(
    db,
    user_id: str,
    name: str,
    tool_input: Dict[str, Any],
    session_id: str,
    caller_profile_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Ejecuta una tool y trunca el resultado."""
    if name in _LEGACY:
        result = await bedrock_service._execute_tool(
            db, user_id, name, tool_input, session_id, caller_profile_id=caller_profile_id
        )
    else:
        result = await _execute_extended(db, user_id, name, tool_input, session_id)
    return truncate_tool_result(result)


def is_write_tool(name: str) -> bool:
    return name in _WRITE_TOOLS


def invalidation_key(name: str, tool_input: Dict[str, Any], tool_result: Dict[str, Any]) -> Optional[str]:
    """Clave para invalidar caché del admin tras un write exitoso (career resource_key o dominio especial)."""
    if tool_result.get("error"):
        return None
    if name == "bulk_update_career_record" and not tool_result.get("updated_count"):
        # Nada se escribió realmente (todos los items fallaron) — no invalidar caché.
        return None
    if tool_input.get("resource_key"):
        return str(tool_input["resource_key"])
    if name in ("pdf_template", "create_pdf_template", "update_pdf_template") or name in _PDF_TEMPLATE_ALIASES:
        action = tool_input.get("action") or _PDF_TEMPLATE_ALIASES.get(name)
        if action in ("create", "update") or name in ("create_pdf_template", "update_pdf_template"):
            return "pdf-templates"
    if name in ("pdf_style", "create_pdf_template_style", "update_pdf_template_style") or name in _PDF_STYLE_ALIASES:
        action = tool_input.get("action") or _PDF_STYLE_ALIASES.get(name)
        if action in ("create", "update") or name in ("create_pdf_template_style", "update_pdf_template_style"):
            return "pdf-template-styles"
    if name == "save_job_listings":
        return "vacancies"
    if name in ("generate_pdf", "render_record_pdf"):
        return tool_input.get("resource_key") or "files"
    if name == "agent_catalog_settings":
        action = tool_input.get("action")
        if action in ("update_prompt", "update_delegation", "update_methodologies"):
            return "agent-profiles"
    if name == "admin_section_settings" and tool_input.get("action") == "update":
        return "admin-sections"
    if name == "bedrock_global_settings" and tool_input.get("action") in (
        "update_system_prompt",
        "update_global_rules",
    ):
        return "bedrock-settings"
    if name == "error_report_settings" and tool_input.get("action") in ("resolve", "reopen"):
        return "error-reports"
    return None
