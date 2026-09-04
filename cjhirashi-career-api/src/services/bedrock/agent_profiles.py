"""
Perfiles de agente — jerarquía de 3 niveles (ADR-012).

Nivel 1: orquestador (chat general). Sin CRUD; solo delega.
Nivel 2: especialistas de área (chat contextual). Dueños de su dominio; delegan a L3.
Nivel 3: especialistas de tarea (sin chat). Workers internos.

Espejo UI user-facing: admin/src/config/agentProfiles.ts
"""
from dataclasses import dataclass
from typing import List, Optional, Set


# ============================================================================
# Definición del perfil de agente
# ============================================================================

@dataclass(frozen=True)
class AgentProfile:
    id: str
    label: str
    domain_keys: List[str]
    resource_keys: Optional[List[str]]
    methodology_sections: List[str]
    system_prompt_suffix: str
    default_model_id: Optional[str]
    allowed_tool_names: Optional[Set[str]] = None
    write_enabled: bool = True
    level: int = 2

    @property
    def can_delegate(self) -> bool:
        return self.level in (1, 2)

    @property
    def user_facing(self) -> bool:
        return self.level in (1, 2)


# ============================================================================
# IDs: agent_<english_label> (L1/L2) o agent_<task> (L3)
# ============================================================================

AGENT_ORCHESTRATOR = "agent_orchestrator"
AGENT_PROFESSIONAL_IDENTITY = "agent_professional_identity"
AGENT_SEARCH_OPERATIONS = "agent_search_operations"
AGENT_DIGITAL_PRESENCE = "agent_digital_presence"
AGENT_NETWORKING = "agent_networking"
AGENT_SUPPORT = "agent_support"
AGENT_METHODOLOGIES = "agent_methodologies"
AGENT_PDF_DESIGN = "agent_pdf_design"
AGENT_PDF_RENDER = "agent_pdf_render"
AGENT_VISUAL_DESIGN = "agent_visual_design"
AGENT_CHANGELOG = "agent_changelog"
AGENT_TASK_MANAGER = "agent_task_manager"
AGENT_LINKEDIN_PUBLISHING = "agent_linkedin_publishing"
AGENT_VACANCY_SEARCH = "agent_vacancy_search"
AGENT_CV_WRITING = "agent_cv_writing"
AGENT_COVER_LETTER_WRITING = "agent_cover_letter_writing"
AGENT_WEB_SEARCH = "agent_web_search"
AGENT_GITHUB = "agent_github"
AGENT_SETTINGS = "agent_settings"
AGENT_CONFIGURATION = "agent_configuration"

# PK de catálogo (formato PREFIX-n, igual que el resto de tablas).
# `agent_*` sigue siendo el nombre de sistema usado en código, FKs y Bedrock.
_AGENT_RECORD_IDS: dict[str, str] = {
    AGENT_ORCHESTRATOR: "agent-1",
    AGENT_PROFESSIONAL_IDENTITY: "agent-2",
    AGENT_SEARCH_OPERATIONS: "agent-3",
    AGENT_DIGITAL_PRESENCE: "agent-4",
    AGENT_NETWORKING: "agent-5",
    AGENT_SUPPORT: "agent-6",
    AGENT_METHODOLOGIES: "agent-7",
    AGENT_PDF_DESIGN: "agent-8",
    AGENT_PDF_RENDER: "agent-9",
    AGENT_VISUAL_DESIGN: "agent-10",
    AGENT_CHANGELOG: "agent-11",
    AGENT_TASK_MANAGER: "agent-12",
    AGENT_LINKEDIN_PUBLISHING: "agent-13",
    AGENT_VACANCY_SEARCH: "agent-14",
    AGENT_CV_WRITING: "agent-15",
    AGENT_COVER_LETTER_WRITING: "agent-16",
    AGENT_WEB_SEARCH: "agent-17",
    AGENT_GITHUB: "agent-18",
    AGENT_SETTINGS: "agent-19",
    # ADR-022: numeración congelada y a mano; agent-20 es el siguiente entero libre.
    AGENT_CONFIGURATION: "agent-20",
}
_PROFILE_BY_RECORD_ID: dict[str, str] = {record_id: key for key, record_id in _AGENT_RECORD_IDS.items()}

# ============================================================================
# Constantes y recursos por dominio
# ============================================================================

_L2_BASE_TOOL_NAMES = {
    "describe_resource_schema",
    "search_knowledge_base",
    "list_career_record",
    "count_career_records",
    "get_career_record",
    "create_career_record",
    "update_career_record",
    "bulk_update_career_record",
    "delete_career_record",
}

_LINKEDIN_TOOL_NAMES = {
    "get_linkedin_status",
    "list_linkedin_posts",
    "create_linkedin_post",
    "delete_scheduled_linkedin_post",
}

_JOB_DISCOVERY_TOOL_NAMES = {
    "list_job_providers",
    "run_job_discovery",
    "import_job_url",
    "save_job_listings",
}

_PDF_DESIGN_TOOL_NAMES = {
    "search_knowledge_base",
    "pdf_template",
    "pdf_style",
    "describe_resource_schema",
}

_PDF_RENDER_TOOL_NAMES = {
    "list_pdf_capable_resources",
    "generate_pdf",
    "render_record_pdf",
}

_VISUAL_TOOL_NAMES = {
    "generate_image",
    "store_uploaded_image",
    "attach_image_to_record",
    "list_generated_images",
    "search_knowledge_base",
    "update_career_record",
    "bulk_update_career_record",
}

_CHANGELOG_TOOL_NAMES = {
    "list_recent_changes",
    "restore_deleted_record",
}

_TASK_MANAGER_TOOL_NAMES = {
    "describe_resource_schema",
    "list_career_record",
    "count_career_records",
    "get_career_record",
    "create_career_record",
    "update_career_record",
    "bulk_update_career_record",
    "delete_career_record",
}

_LINKEDIN_PUBLISHING_TOOL_NAMES = set(_LINKEDIN_TOOL_NAMES)

_VACANCY_SEARCH_TOOL_NAMES = set(_JOB_DISCOVERY_TOOL_NAMES)

_DOCUMENT_WRITING_TOOL_NAMES = {
    "describe_resource_schema",
    "search_knowledge_base",
    "list_career_record",
    "count_career_records",
    "get_career_record",
    "create_career_record",
    "update_career_record",
    "bulk_update_career_record",
    "delete_career_record",
}

_WEB_SEARCH_TOOL_NAMES = {
    "web_search",
    "web_fetch",
}

_GITHUB_TOOL_NAMES = {
    "get_github_status",
    "list_github_repos",
    "get_github_repo",
    "list_github_contents",
    "get_github_file",
    "search_github_code",
}

# ADR-022: `agent_configuration` (agent-20) opera la metaconfiguración del harness;
# `agent_settings` (agent-19) queda solo con incidencias y bitácora.
_CONFIGURATION_TOOL_NAMES = {
    "search_knowledge_base",
    "agent_catalog_settings",
    "admin_section_settings",
    "bedrock_global_settings",
}

_SETTINGS_TOOL_NAMES = {
    "search_knowledge_base",
    "error_report_settings",
}

_DIGITAL_RESOURCES = [
    "linkedin-profile",
    "github-profile",
    "portal-home",
    "portal-about",
    "portal-contact",
    "publications",
]

_IDENTITY_RESOURCES = [
    "personal-profile",
    "differentiators",
    "identity",
    "identity-reflections",
    "competencies",
    "certifications",
    "target-roles",
    "work-history",
    "achievements",
    "star-stories",
    "career-reviews",
    "role-gap-analysis",
    "projects",
]

_SEARCH_RESOURCES = [
    "fit-scoring-factors",
    "market-segments",
    "role-narratives",
    "search-plans",
    "networking-contacts",
    "target-companies",
    "vacancies",
    "cv-versions",
    "cover-letter-versions",
    "applications",
    "application-interactions",
    "interviews",
]

# ============================================================================
# Suffix del perfil agent_pdf_design (modelo estilos + plantillas)
# ============================================================================

_PDF_DESIGN_SUFFIX = (
    "Eres PDF Maker, especialista L2 de diseño PDF (WeasyPrint). El sistema separa CSS y HTML en dos tablas "
    "relacionadas — NUNCA mezcles CSS dentro de plantillas:\n"
    "1) **Estilos** (`pdf-template-styles`, IDs `pds-N`): guardan `css_content` (CSS completo) y "
    "`style_guide` (Markdown que documenta clases, etiquetas y selectores disponibles).\n"
    "2) **Plantillas** (`pdf-output-templates`, IDs `pdt-N`): guardan `html_template` (HTML con "
    "{{variables}}`), `style_id` (FK → `pds-N`) y `variables` (Markdown que documenta cada "
    "placeholder y qué contenido debe llevar).\n"
    "Relación: **un estilo, muchas plantillas**. Varias plantillas pueden compartir el mismo "
    "`style_id`. No generas el PDF final: para previsualizar o emitir un documento delega a "
    "`agent_pdf_render` (L3) con generate_pdf / render_record_pdf.\n"
    "Tools reales: `pdf_style` y `pdf_template` (action=list|get|create|update). No existen tools "
    "llamadas `update_pdf_template_style` ni `create_pdf_template`.\n"
    "Persistencia: redactar Markdown o HTML en el chat NO guarda nada en PostgreSQL. Para guardar "
    "la guía de clases llama `pdf_style` con action=update, style_id (ej. pds-1) y style_guide. "
    "Para HTML usa `pdf_template` action=create o update. Prohibido decir que actualizaste un "
    "registro hasta que la tool devuelva el id.\n"
    "Flujo de diseño: (a) pdf_style action=get o create; (b) pdf_style action=update con style_guide; "
    "(c) pdf_template action=create con style_id y variables. Si reutilizas un estilo, lee su "
    "style_guide antes de escribir HTML. Consulta `search_knowledge_base` (type=methodology) "
    "solo para las metodologías asignadas a este perfil."
)

_METHODOLOGIES_SUFFIX = (
    "Eres el guardián L2 de metodologías operativas. Solo operas "
    "`operational-methodologies` (IDs `opm-N`). Campo de cuerpo: `content` (Markdown). "
    "También title, section, subsection, description, notes y agent_profile_ids "
    "(lista de ids agent_*; vacío = todos los agentes).\n"
    "Persistencia: redactar Markdown en el chat NO guarda nada en PostgreSQL. "
    "Para actualizar un registro existente llama `update_career_record` con "
    "resource_key='operational-methodologies', record_id (ej. opm-57) y fields.content "
    "con el Markdown completo. Para uno nuevo llama `create_career_record` con "
    "fields.title, fields.section y fields.content.\n"
    "Prohibido decir que actualizaste o guardaste hasta que la tool devuelva el id. "
    "Si Carlos dice procede, adelante o hazlo, llama la tool EN ESTE TURNO sin anunciar "
    "primero. No sustituyas la escritura por un plan en agent-tasks: actualizar un opm-N "
    "es un solo update_career_record. "
    "Al crear o editar, usa agent_profile_ids para asignar la metodología al agente dueño; "
    "ese agente la asume como suya en el siguiente turno. Vacío = compartida (todos). "
    "Bitácora → agent_changelog; plan multi-paso → agent_task_manager."
)

_ORCHESTRATOR_SUFFIX = (
    "Eres el orquestador (nivel 1) del gestor de carrera. No operas tablas ni generas PDFs, "
    "imágenes o bitácora tú mismo. Siempre delega con delegate_to_specialist:\n"
    "- Dominio de carrera → L2 dueño del área (agent_professional_identity, "
    "agent_search_operations, agent_digital_presence, agent_networking, agent_support, "
    "agent_methodologies, agent_pdf_design).\n"
    "- Configuración del sistema (catálogo de agentes, secciones del Admin, prompts "
    "globales) → agent_configuration.\n"
    "- Reportes de falla / bitácora de cambios del agente → agent_settings.\n"
    "- Tarea transversal → L3 (agent_pdf_render, agent_visual_design, agent_changelog, "
    "agent_task_manager, agent_linkedin_publishing, agent_vacancy_search, "
    "agent_cv_writing, agent_cover_letter_writing, agent_web_search, agent_github).\n"
    "Resume en español claro para Carlos solo lo que devolvieron los especialistas. "
    "Discovery de vacantes → agent_vacancy_search (preview refs L1, L2…; no guarda "
    "hasta que Carlos autorice). Pipeline de vacantes/apps → agent_search_operations. "
    "Redactar un CV → agent_cv_writing. Cover letter → agent_cover_letter_writing. "
    "PDF de un registro ya redactado → agent_pdf_render. "
    "Publicar o programar en LinkedIn → agent_linkedin_publishing. "
    "Consulta web (buscar o leer una URL) → agent_web_search. "
    "Repos GitHub en vivo → agent_github. Nunca inventes vacantes."
)

_CONFIGURATION_SUFFIX = (
    "Eres el especialista L2 de Configuración: metaconfiguración del harness de agentes. "
    "Administras tres áreas, cada una con su propia tool — no son tablas de carrera, no uses "
    "create/update_career_record:\n"
    "1) **Catálogo de agentes** — prompt suffix, destinos de delegación y metodologías "
    "asignadas por perfil. Tool `agent_catalog_settings` (action=list|get|update_prompt|"
    "update_delegation|update_methodologies, profile_id).\n"
    "2) **Secciones del Admin** — qué agente domina cada pantalla y su descripción. "
    "Tool `admin_section_settings` (action=list|get|update, section_id, agent_profile_id, "
    "description). `section_id` es el PK `sec-N` (p.ej. sec-1); toma el campo `id` de "
    "action=list. `system_name` (dashboard, career-projects…) es solo el nombre legible.\n"
    "3) **Prompts globales** — system prompt base y reglas globales (grounding + asignación "
    "de metodologías) que aplican a TODOS los agentes. Tool `bedrock_global_settings` "
    "(action=get|update_system_prompt|update_global_rules).\n"
    "No tocas fotos de agente: eso es agent_visual_design con resource_key=agent-profile. "
    "No tocas operational-methodologies (contenido de las metodologías): eso es "
    "agent_methodologies; tú solo asignas cuáles consulta cada agente. "
    "Reportes de falla y bitácora de cambios del agente son de agent_settings, no tuyos. "
    "Redactar en el chat NO guarda nada: llama la tool correspondiente con el campo a "
    "cambiar. No afirmes que guardaste hasta que la tool devuelva el resultado. "
    "Un override de prompt (de perfil o global) aplica desde el siguiente turno de ese "
    "agente; string vacío o null en el campo de texto restaura el default del código. "
    "Bitácora → agent_changelog."
)

_SETTINGS_SUFFIX = (
    "Eres el especialista L2 de Incidencias y Bitácora. Cubres dos áreas de observación — "
    "no cambian el comportamiento de los agentes, se consultan y se resuelven/restauran:\n"
    "1) **Reportes de falla** — bitácora de errores del sistema (tabla error_reports, IDs err-N). "
    "Tool `error_report_settings` (action=list|get|resolve|reopen|summary, report_id). "
    "Marca un reporte como resuelto SOLO cuando el problema ya se corrigió en el código.\n"
    "2) **Bitácora de cambios del agente** (`/agent/audit-log`) — para inspeccionar o restaurar "
    "create/update/delete que hicieron los agentes, delega a `agent_changelog` (L3) con "
    "list_recent_changes / restore_deleted_record. No recrees registros a mano.\n"
    "No editas catálogo de agentes, secciones del Admin ni prompts globales: eso es "
    "agent_configuration. "
    "Redactar en el chat NO guarda nada: llama la tool correspondiente. No afirmes que "
    "resolviste o restauraste hasta que la tool devuelva el resultado."
)

_PDF_RENDER_SUFFIX = (
    "Eres el renderizador PDF (nivel 3). No hablas con el usuario ni editas plantillas o estilos. "
    "Tablas con función PDF: cv-versions (campo content, document_type=cv) y "
    "cover-letter-versions (campo body_content, document_type=cover_letter). "
    "Usa list_pdf_capable_resources si dudas. Para un registro: render_record_pdf "
    "(resource_key + record_id; template_id opcional, si falta usa la plantilla default del tipo). "
    "Para preview de plantilla: generate_pdf (template_id + variables). "
    "Devuelve pdf_url, filename y el registro tocado. No afirmes que generaste un archivo "
    "hasta que la tool devuelva la URL."
)

_LINKEDIN_PUBLISHING_SUFFIX = (
    "Eres el controlador L3 de publicación LinkedIn. No hablas con el usuario ni editas "
    "perfiles, portal ni publicaciones del portafolio. "
    "Tools: get_linkedin_status, list_linkedin_posts, create_linkedin_post, "
    "delete_scheduled_linkedin_post. "
    "Publica ahora (sin scheduled_at) o programa (ISO futuro) solo si la tarea trae el texto. "
    "No inventes copy. Si falta conexión, llama get_linkedin_status y reporta el error. "
    "Devuelve ids, estado (published|scheduled|failed) y scheduled_at. "
    "No afirmes que publicaste hasta que la tool lo confirme."
)

_VACANCY_SEARCH_SUFFIX = (
    "Eres el controlador L3 de búsqueda de vacantes. No hablas con el usuario ni operas "
    "el pipeline de CVs, aplicaciones o entrevistas. "
    "Flujo: (1) run_job_discovery — preview con refs L1, L2…, no escribe vacancies. "
    "Indeed: providers=['indeed'] (vía Adzuna). "
    "LinkedIn: providers=['linkedin'] solo arma URLs oficiales de búsqueda; "
    "luego import_job_url con cada linkedin.com/jobs/view que venga en la tarea. "
    "No inventes vacantes de LinkedIn. Get on Board, Remotive y RemoteOK sí listan vacantes. "
    "(2) Devuelve cada oferta con ref, empresa, rol, fuente, ubicación, URL y already_saved. "
    "(3) save_job_listings({refs: ['L1','L3']}) solo si la tarea trae refs autorizadas por Carlos; "
    "crea vacancies con evaluation=pending_review. "
    "Si la tarea trae una URL concreta, importar y guardar esa ref en el mismo turno sí está autorizado. "
    "Nunca uses create_career_record. list_job_providers para listar fuentes. "
    "No afirmes que guardaste vacantes hasta que save_job_listings lo confirme."
)

_CV_WRITING_SUFFIX = (
    "Eres el redactor L3 de CVs. No hablas con el usuario. Solo operas `cv-versions`. "
    "Campo de cuerpo: `content` (Markdown). Status: draft|approved|final. "
    "IDs prefijados cvv-N. Relaciona `target_role_id` y `target_vacancy_ids` si la tarea los trae. "
    "Lee `personal-profile` (nombre, contacto, ubicación, idiomas) e identidad, historial, logros y competencias "
    "con get/list/search antes de inventar hechos. "
    "Si falta evidencia en PG, dilo; no rellenes con supuestos. "
    "Persiste con create_career_record o update_career_record (resource_key=cv-versions). "
    "Redactar en el resumen NO guarda. No afirmes un id hasta que la tool lo devuelva. "
    "No generas PDF: eso es agent_pdf_render. No toques cover-letter-versions ni vacancies."
)

_WEB_SEARCH_SUFFIX = (
    "Eres el controlador L3 de consulta web. No hablas con el usuario ni editas "
    "tablas de carrera. Tools: web_search (buscar en internet) y web_fetch (leer una URL). "
    "Usa web_search para encontrar fuentes; web_fetch solo con URLs http/https públicas "
    "que vinieron de la búsqueda o de la tarea. No inventes URLs ni citas. "
    "Devuelve títulos, URLs y un resumen factual. Si la tool falla, reporta el error."
)

_GITHUB_SUFFIX = (
    "Eres el controlador L3 de GitHub. No hablas con el usuario ni editas github-profile "
    "ni el portal. Solo lectura. Tools: get_github_status, list_github_repos, get_github_repo, "
    "list_github_contents, get_github_file, search_github_code. "
    "Si falta GITHUB_TOKEN, get_github_status lo dice y list_github_repos cae al username "
    "público de github-profile. owner/repo puede ir junto (cjhirashi/portafolio) o separado. "
    "No crees issues, PRs ni pushes. No afirmes un archivo o repo hasta que la tool lo devuelva."
)

_COVER_LETTER_WRITING_SUFFIX = (
    "Eres el redactor L3 de cover letters. No hablas con el usuario. "
    "Solo operas `cover-letter-versions`. Campo de cuerpo: `body_content` (Markdown). "
    "Status: draft|approved|final. IDs prefijados clv-N. "
    "Relaciona `target_role_id` y `target_vacancy_id` si la tarea los trae. "
    "Adapta tono y hechos al rol/vacante; lee esos registros y la evidencia de carrera antes de escribir. "
    "Si falta evidencia en PG, dilo; no inventes logros. "
    "Persiste con create_career_record o update_career_record (resource_key=cover-letter-versions). "
    "Redactar en el resumen NO guarda. No afirmes un id hasta que la tool lo devuelva. "
    "No generas PDF: eso es agent_pdf_render. No toques cv-versions ni vacancies."
)


# ============================================================================
# Definiciones de perfiles
# ============================================================================

_PROFILES: dict[str, AgentProfile] = {
    AGENT_ORCHESTRATOR: AgentProfile(
        id=AGENT_ORCHESTRATOR,
        label="Orquestador",
        domain_keys=[],
        resource_keys=None,
        methodology_sections=[],
        system_prompt_suffix=_ORCHESTRATOR_SUFFIX,
        default_model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        allowed_tool_names={"delegate_to_specialist"},
        level=1,
    ),
    AGENT_PROFESSIONAL_IDENTITY: AgentProfile(
        id=AGENT_PROFESSIONAL_IDENTITY,
        label="Identidad Profesional",
        domain_keys=["identity"],
        resource_keys=_IDENTITY_RESOURCES,
        methodology_sections=["Identidad Profesional"],
        system_prompt_suffix=(
            "Especialista L2 en identidad profesional, competencias y evidencia. "
            "`personal-profile` es la ficha biográfica de referencia (nombre legal, fecha de nacimiento, "
            "ubicación, contacto, idiomas, autorización de trabajo). Léela antes de redactar narrativa, "
            "CVs o formularios; no la confundas con `identity` (tagline, bio y UVP). "
            "Opera solo ese dominio. Bitácora → agent_changelog; PDF de un registro → agent_pdf_render; "
            "imágenes → agent_visual_design; plan de pasos → agent_task_manager; "
            "redacción de CV → agent_cv_writing; cover letter → agent_cover_letter_writing; "
            "consulta web → agent_web_search."
        ),
        # Haiku 4.5: maneja los registros más grandes del sistema (projects,
        # star-stories, work-history), es más barato que Mistral Large y soporta
        # prompt caching (ADR-019 / ADR-012).
        default_model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        level=2,
    ),
    AGENT_SEARCH_OPERATIONS: AgentProfile(
        id=AGENT_SEARCH_OPERATIONS,
        label="Operativa de Búsqueda",
        domain_keys=["search"],
        resource_keys=_SEARCH_RESOURCES,
        methodology_sections=["Operativa de Búsqueda"],
        system_prompt_suffix=(
            "Especialista L2 en pipeline de búsqueda, vacantes, aplicaciones y entrevistas. "
            "No ejecutas discovery ni importas URLs: delega a agent_vacancy_search. "
            "No redactas CVs ni cover letters: delega a agent_cv_writing o "
            "agent_cover_letter_writing. "
            "Flujo: (1) delega la búsqueda/preview; (2) muestra a Carlos cada oferta con ref, "
            "empresa, rol, fuente, ubicación y URL (marca already_saved); "
            "(3) ESPERA autorización explícita (L1 y L3, todas, todas menos L2); "
            "(4) delega save de las refs autorizadas. "
            "Si Carlos pega una URL concreta, delega importar y guardar esa ref en el mismo turno. "
            "Nunca uses create_career_record para ofertas de discovery. "
            "PDF de un CV o carta ya redactados → agent_pdf_render. "
            "Investigar una empresa o tecnología en internet → agent_web_search. "
            "Bitácora → agent_changelog; imágenes → agent_visual_design; plan → agent_task_manager."
        ),
        default_model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        level=2,
    ),
    AGENT_DIGITAL_PRESENCE: AgentProfile(
        id=AGENT_DIGITAL_PRESENCE,
        label="Presencia Digital",
        domain_keys=["digital"],
        resource_keys=_DIGITAL_RESOURCES,
        methodology_sections=["Presencia Digital"],
        system_prompt_suffix=(
            "Especialista L2 en presencia digital, publicaciones del portal y perfiles sociales. "
            "No publicas ni programas posts de LinkedIn: delega a agent_linkedin_publishing. "
            "Repos, archivos o estado de GitHub en vivo → agent_github "
            "(github-profile es ficha CRUD, no la API). "
            "Consulta web → agent_web_search. "
            "Imágenes → agent_visual_design; bitácora → agent_changelog; PDF → agent_pdf_render; "
            "plan → agent_task_manager."
        ),
        default_model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        level=2,
    ),
    AGENT_NETWORKING: AgentProfile(
        id=AGENT_NETWORKING,
        label="Networking",
        domain_keys=["networking"],
        resource_keys=["contact-interactions", "networking-activities"],
        methodology_sections=["Networking"],
        system_prompt_suffix=(
            "Especialista L2 en contactos y seguimiento de networking. "
            "Bitácora → agent_changelog; plan → agent_task_manager."
        ),
        default_model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        level=2,
    ),
    AGENT_SUPPORT: AgentProfile(
        id=AGENT_SUPPORT,
        label="Soporte",
        domain_keys=["support"],
        resource_keys=["tags"],
        methodology_sections=["Soporte"],
        system_prompt_suffix=(
            "Especialista L2 en taxonomía y tags. Bitácora → agent_changelog; plan → agent_task_manager."
        ),
        default_model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        level=2,
    ),
    AGENT_METHODOLOGIES: AgentProfile(
        id=AGENT_METHODOLOGIES,
        label="Metodologías",
        domain_keys=["meta"],
        resource_keys=["operational-methodologies"],
        methodology_sections=[],
        system_prompt_suffix=_METHODOLOGIES_SUFFIX,
        default_model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        level=2,
    ),
    AGENT_PDF_DESIGN: AgentProfile(
        id=AGENT_PDF_DESIGN,
        label="Diseño PDF",
        domain_keys=["document_output"],
        resource_keys=["pdf-output-templates", "pdf-template-styles"],
        methodology_sections=["Diseño PDF"],
        system_prompt_suffix=_PDF_DESIGN_SUFFIX,
        default_model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        allowed_tool_names=_PDF_DESIGN_TOOL_NAMES,
        level=2,
    ),
    AGENT_PDF_RENDER: AgentProfile(
        id=AGENT_PDF_RENDER,
        label="Renderizado PDF",
        domain_keys=["document_output"],
        resource_keys=["cv-versions", "cover-letter-versions"],
        methodology_sections=["Diseño PDF"],
        system_prompt_suffix=_PDF_RENDER_SUFFIX,
        default_model_id="amazon.nova-lite-v1:0",
        allowed_tool_names=_PDF_RENDER_TOOL_NAMES,
        level=3,
    ),
    AGENT_VISUAL_DESIGN: AgentProfile(
        id=AGENT_VISUAL_DESIGN,
        label="Agente Visual",
        domain_keys=["visual_media"],
        resource_keys=None,
        methodology_sections=["Diseño Visual"],
        system_prompt_suffix=(
            "Especialista L3 de imágenes. No hablas con el usuario. "
            "Tres secciones de bucket, cada una con su medida fija: agentes (foto de catálogo, 500x500), "
            "proyectos (1920x1080), publicaciones (1920x1080). Todo PNG comprimido para web. "
            "Si quien delega ya tiene una imagen (adjunta, file_id) y solo quiere guardarla/optimizarla, "
            "usa store_uploaded_image (NO generes nada nuevo). Si no tiene imagen, pide o usa el prompt y "
            "usa generate_image (Titan). Paleta cyan #0891B2, estilo profesional/tecnológico para lo que generes. "
            "Nombra el archivo de forma legible (name). Al terminar, devuelve la image_url a quien delegó "
            "para que la cargue en su registro (o usa attach_image_to_record si te dan resource_key/record_id, "
            "incluyendo agent-profile para fotos del catálogo). No afirmes un adjunto hasta que la tool confirme."
        ),
        default_model_id="amazon.nova-lite-v1:0",
        allowed_tool_names=_VISUAL_TOOL_NAMES,
        level=3,
    ),
    AGENT_CHANGELOG: AgentProfile(
        id=AGENT_CHANGELOG,
        label="Gestor de bitácora",
        domain_keys=["meta"],
        resource_keys=None,
        methodology_sections=[],
        system_prompt_suffix=(
            "Especialista L3 de bitácora. No hablas con el usuario. "
            "Usa list_recent_changes para inspeccionar create/update/delete del agente. "
            "Si piden deshacer un delete, restaura con restore_deleted_record (audit_id); "
            "no recrees el registro a mano. Resume qué cambió, cuándo y el audit_id."
        ),
        default_model_id="amazon.nova-lite-v1:0",
        allowed_tool_names=_CHANGELOG_TOOL_NAMES,
        level=3,
    ),
    AGENT_TASK_MANAGER: AgentProfile(
        id=AGENT_TASK_MANAGER,
        label="Gestor de tareas",
        domain_keys=["meta"],
        resource_keys=["agent-tasks"],
        methodology_sections=[],
        system_prompt_suffix=(
            "Especialista L3 del tablero de tareas (resource_key agent-tasks). No hablas con el usuario. "
            "Campos: title, description, status (pending|in_progress|done|cancelled|failed), "
            "assignee_type (user|agent), agent_profile_id (obligatorio si agent), "
            "scheduled_at (ISO UTC: cuándo debe ejecutar el agente si no es por turno), due_at, "
            "priority (low|medium|high), parent_id (subtarea de un plan), sort_order, "
            "is_blocking (si True, las hermanas posteriores esperan a done/cancelled), "
            "execute_on_turn (agente: corre al desbloquearse, sin esperar scheduled_at). "
            "Un padre con hijas es el orquestador: no lo ejecutes como agente. "
            "Si Carlos pide que un agente haga algo a cierta hora, crea la fila con "
            "assignee_type=agent, el agent_profile_id del especialista adecuado y scheduled_at. "
            "Si pide un plan con pasos, crea el padre y subtareas (parent_id). "
            "El scheduler las ejecuta aunque Carlos no esté en sesión; si el responsable es user, "
            "se le notifica cuando le toca el turno. "
            "El scheduler la ejecutará aunque Carlos no esté en sesión. "
            "No uses agent-tasks solo como checklist de un turno si la petición es programar trabajo. "
            "Solo opera agent-tasks. Devuelve ids y el estado."
        ),
        default_model_id="amazon.nova-lite-v1:0",
        allowed_tool_names=_TASK_MANAGER_TOOL_NAMES,
        level=3,
    ),
    AGENT_LINKEDIN_PUBLISHING: AgentProfile(
        id=AGENT_LINKEDIN_PUBLISHING,
        label="Control de publicación LinkedIn",
        domain_keys=["digital"],
        resource_keys=None,
        methodology_sections=["Presencia Digital"],
        system_prompt_suffix=_LINKEDIN_PUBLISHING_SUFFIX,
        default_model_id="amazon.nova-lite-v1:0",
        allowed_tool_names=_LINKEDIN_PUBLISHING_TOOL_NAMES,
        level=3,
    ),
    AGENT_VACANCY_SEARCH: AgentProfile(
        id=AGENT_VACANCY_SEARCH,
        label="Control de búsqueda de vacantes",
        domain_keys=["search"],
        resource_keys=None,
        methodology_sections=["Operativa de Búsqueda"],
        system_prompt_suffix=_VACANCY_SEARCH_SUFFIX,
        default_model_id="amazon.nova-lite-v1:0",
        allowed_tool_names=_VACANCY_SEARCH_TOOL_NAMES,
        level=3,
    ),
    AGENT_CV_WRITING: AgentProfile(
        id=AGENT_CV_WRITING,
        label="Redacción de CVs",
        domain_keys=["search"],
        resource_keys=["cv-versions"],
        methodology_sections=["Operativa de Búsqueda"],
        system_prompt_suffix=_CV_WRITING_SUFFIX,
        default_model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        allowed_tool_names=_DOCUMENT_WRITING_TOOL_NAMES,
        level=3,
    ),
    AGENT_COVER_LETTER_WRITING: AgentProfile(
        id=AGENT_COVER_LETTER_WRITING,
        label="Redacción de cover letters",
        domain_keys=["search"],
        resource_keys=["cover-letter-versions"],
        methodology_sections=["Operativa de Búsqueda"],
        system_prompt_suffix=_COVER_LETTER_WRITING_SUFFIX,
        default_model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        allowed_tool_names=_DOCUMENT_WRITING_TOOL_NAMES,
        level=3,
    ),
    AGENT_WEB_SEARCH: AgentProfile(
        id=AGENT_WEB_SEARCH,
        label="Consulta web",
        domain_keys=["search"],
        resource_keys=None,
        methodology_sections=[],
        system_prompt_suffix=_WEB_SEARCH_SUFFIX,
        default_model_id="amazon.nova-lite-v1:0",
        allowed_tool_names=_WEB_SEARCH_TOOL_NAMES,
        write_enabled=False,
        level=3,
    ),
    AGENT_GITHUB: AgentProfile(
        id=AGENT_GITHUB,
        label="Control GitHub",
        domain_keys=["digital"],
        resource_keys=None,
        methodology_sections=["Presencia Digital"],
        system_prompt_suffix=_GITHUB_SUFFIX,
        default_model_id="amazon.nova-lite-v1:0",
        allowed_tool_names=_GITHUB_TOOL_NAMES,
        write_enabled=False,
        level=3,
    ),
    AGENT_SETTINGS: AgentProfile(
        id=AGENT_SETTINGS,
        # ADR-022: se conserva el system-name `agent_settings` (FK en 4 tablas);
        # solo cambian label, suffix y tools — ahora cubre incidencias y bitácora.
        label="Incidencias y Bitácora",
        domain_keys=["meta_settings"],
        resource_keys=None,
        methodology_sections=[],
        system_prompt_suffix=_SETTINGS_SUFFIX,
        default_model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        allowed_tool_names=_SETTINGS_TOOL_NAMES,
        level=2,
    ),
    AGENT_CONFIGURATION: AgentProfile(
        id=AGENT_CONFIGURATION,
        label="Configuración",
        domain_keys=["meta_settings"],
        resource_keys=None,
        methodology_sections=[],
        system_prompt_suffix=_CONFIGURATION_SUFFIX,
        default_model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        allowed_tool_names=_CONFIGURATION_TOOL_NAMES,
        level=2,
    ),
}


# ============================================================================
# Mapas de enrutamiento
# ============================================================================

_ROUTE_TO_PROFILE = {
    "/linkedin": AGENT_DIGITAL_PRESENCE,
    "/job-discovery": AGENT_SEARCH_OPERATIONS,
    "/career/publications": AGENT_DIGITAL_PRESENCE,
    "/career/operational-methodologies": AGENT_METHODOLOGIES,
    "/agent/chat": AGENT_ORCHESTRATOR,
    "/agent/pdf-templates": AGENT_PDF_DESIGN,
    "/agent/pdf-template-styles": AGENT_PDF_DESIGN,
    "/settings/agents": AGENT_CONFIGURATION,
    "/settings/sections": AGENT_CONFIGURATION,
    "/settings/agent-prompts": AGENT_CONFIGURATION,
    "/settings/error-reports": AGENT_SETTINGS,
    "/agent/audit-log": AGENT_SETTINGS,
}

_RESOURCE_TO_DOMAIN = {
    **{k: "identity" for k in _IDENTITY_RESOURCES},
    **{k: "search" for k in _SEARCH_RESOURCES},
    **{k: "digital" for k in _DIGITAL_RESOURCES},
    "contact-interactions": "networking",
    "networking-activities": "networking",
    "tags": "support",
    "operational-methodologies": "methodologies",
    "pdf-output-templates": "document_output",
    "pdf-template-styles": "document_output",
}

_DOMAIN_TO_PROFILE = {
    "identity": AGENT_PROFESSIONAL_IDENTITY,
    "search": AGENT_SEARCH_OPERATIONS,
    "digital": AGENT_DIGITAL_PRESENCE,
    "networking": AGENT_NETWORKING,
    "support": AGENT_SUPPORT,
    "document_output": AGENT_PDF_DESIGN,
}


# ============================================================================
# Resolución de perfil y tools
# ============================================================================

def get_profile(profile_id: str) -> AgentProfile:
    key = _PROFILE_BY_RECORD_ID.get(profile_id, profile_id)
    if key not in _PROFILES:
        raise KeyError(f"Unknown agent profile: {profile_id}")
    return _PROFILES[key]


def agent_record_id(profile_id: str) -> str:
    """PK de catálogo (`agent-1`). Acepta nombre de sistema o el propio record id."""
    key = _PROFILE_BY_RECORD_ID.get(profile_id, profile_id)
    if key not in _AGENT_RECORD_IDS:
        raise KeyError(f"Unknown agent profile: {profile_id}")
    return _AGENT_RECORD_IDS[key]


def canonical_profile_id(profile_id: str) -> str:
    """Nombre de sistema (`agent_orchestrator`)."""
    return get_profile(profile_id).id


def list_profiles() -> List[AgentProfile]:
    return list(_PROFILES.values())


def known_agent_profile_ids() -> set[str]:
    return set(_PROFILES.keys())


def list_user_facing_profiles() -> List[AgentProfile]:
    return [p for p in list_profiles() if p.user_facing]


def can_delegate_to(caller: AgentProfile, target: AgentProfile) -> bool:
    """Delegación solo hacia abajo: L1→L2|L3, L2→L3. Nunca arriba ni al mismo nivel."""
    if caller.level == 1:
        return target.level in (2, 3)
    if caller.level == 2:
        return target.level == 3
    return False


def delegation_error(
    caller: AgentProfile,
    target_id: str,
    allowed_ids: Optional[Set[str]] = None,
) -> Optional[str]:
    """None si la delegación es válida; mensaje de error si no."""
    try:
        target = get_profile(target_id)
    except KeyError:
        return f"unknown agent profile: {target_id}"
    if not can_delegate_to(caller, target):
        return (
            f"delegation not allowed: {caller.id} (L{caller.level}) "
            f"cannot call {target.id} (L{target.level})"
        )
    if allowed_ids is not None and target_id not in allowed_ids:
        return (
            f"delegation not allowed: {target_id} is not in this agent's configured targets"
        )
    return None


def delegation_targets(caller: AgentProfile) -> List[AgentProfile]:
    return [p for p in list_profiles() if can_delegate_to(caller, p)]


def delegate_tool_description(
    caller: AgentProfile,
    target_ids: Optional[List[str]] = None,
) -> str:
    if target_ids is None:
        targets = delegation_targets(caller)
    else:
        targets = []
        for tid in target_ids:
            try:
                targets.append(get_profile(tid))
            except KeyError:
                continue
    if not targets:
        return "Esta herramienta no está disponible para este perfil."
    listed = ", ".join(f"{p.id} ({p.label}, L{p.level})" for p in targets)
    return (
        "Delega a un especialista de nivel inferior. Nunca hacia arriba ni al mismo nivel. "
        f"Destinos permitidos: {listed}. "
        "Pasa task concreta y context breve. El especialista no habla con el usuario; "
        "tú resumes su resultado."
    )


def resolve_agent_profile(
    *,
    chat_surface: str,
    agent_profile_id: Optional[str],
    page_context: Optional[dict],
) -> AgentProfile:
    """Router: chat general → orquestador; contextual → ruta/recurso (solo L1/L2)."""
    if chat_surface == "general":
        return get_profile(AGENT_ORCHESTRATOR)
    if agent_profile_id:
        return get_profile(agent_profile_id)
    if page_context:
        route = page_context.get("route") or ""
        if route in _ROUTE_TO_PROFILE:
            return get_profile(_ROUTE_TO_PROFILE[route])
        prefix_matches = sorted(
            (
                (path, pid)
                for path, pid in _ROUTE_TO_PROFILE.items()
                if route.startswith(f"{path}/")
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        if prefix_matches:
            return get_profile(prefix_matches[0][1])
        rk = page_context.get("resource_key")
        if rk and rk in _RESOURCE_TO_DOMAIN:
            return get_profile(_DOMAIN_TO_PROFILE[_RESOURCE_TO_DOMAIN[rk]])
    return get_profile(AGENT_ORCHESTRATOR)


def tools_for_profile(profile: AgentProfile, all_tool_names: Set[str]) -> Set[str]:
    """Filtra nombres de tool según perfil y nivel."""
    if profile.allowed_tool_names is not None:
        names = set(profile.allowed_tool_names)
    elif profile.level == 1:
        names = {"delegate_to_specialist"}
    else:
        names = set(_L2_BASE_TOOL_NAMES)

    names &= all_tool_names
    if profile.can_delegate:
        names.add("delegate_to_specialist")
    else:
        names.discard("delegate_to_specialist")
    return names


def profile_can_search_knowledge(profile: AgentProfile) -> bool:
    """True si el perfil tiene `search_knowledge_base` (consulta metodologías asignadas)."""
    if profile.allowed_tool_names is not None:
        return "search_knowledge_base" in profile.allowed_tool_names
    return profile.level == 2
