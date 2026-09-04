"""
Punto de entrada de la aplicación FastAPI.

Responsabilidades:
- Lifecycle (startup/shutdown): BD, MinIO, scheduler LinkedIn y tareas de agentes
- Middleware CORS y manejadores globales de errores
- Registro de todos los routers (auth, career, bedrock, public, …)
- Endpoints de sistema: /health, /
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException as FastAPIHTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
import asyncio
import logging
import sys

from config import settings
from database import init_db, close_db
from routes import auth_enhanced
from routes import career_identity, career_search, career_digital, career_support, career_metrics, career_methodologies, job_discovery
from routes import bedrock
from routes import bedrock_tasks
from routes import admin_sections
from routes import pdf_templates, pdf_template_styles
from routes import files
from routes import linkedin
from routes import public
from routes import notifications
from routes import error_reports
from services import storage_service, linkedin_scheduler, task_scheduler
from services.error_reporting import areport_error

# ============================================================================
# Logging
# ============================================================================
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


# ============================================================================
# Lifecycle — startup y shutdown de recursos compartidos
# ============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager para inicializar y cerrar recursos.
    Se ejecuta al inicio y al cierre de la aplicación.
    """
    # Startup
    logger.info("Starting up API server...")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    try:
        storage_service.ensure_bucket()
        logger.info("MinIO bucket ready")
    except Exception as e:
        # Files/uploads will fail until MinIO is reachable, but the rest of
        # the API (career CRUD, PDF templates, auth, Bedrock) must stay up.
        # A hard raise here used to crash uvicorn on a bad MINIO_ENDPOINT,
        # which Cloudflare surfaces as error 520 on every /api request.
        logger.error(
            "Failed to initialize MinIO bucket (%s). File storage is unavailable; other routes will still serve.",
            e,
        )

    linkedin_task = asyncio.create_task(linkedin_scheduler.scheduler_loop())
    agent_task_loop = asyncio.create_task(task_scheduler.scheduler_loop())
    logger.info("LinkedIn post scheduler started")
    logger.info("Agent task scheduler started")

    yield

    # Shutdown
    logger.info("Shutting down API server...")
    linkedin_task.cancel()
    agent_task_loop.cancel()
    await close_db()


# ============================================================================
# Instancia FastAPI
# ============================================================================
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API REST para gestión de documentos con autenticación JWT",
    lifespan=lifespan
)


# ============================================================================
# Middleware CORS
# ============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Manejadores globales de excepciones
# ============================================================================
# Cada falla que llega a un handler global se registra en `error_reports`
# (ADR-018). `REPORT_CLIENT_ERRORS` controla si los 4xx (validación, HTTP
# 400-499) también dejan reporte — útil para ver validaciones fallidas, se
# puede bajar a False si genera demasiado ruido.
REPORT_CLIENT_ERRORS = True

# Rutas cuyo fallo NO se registra (evita bucles y ruido del propio registro).
_ERROR_REPORT_SKIP_PATHS = ("/system/error-report", "/health")


def _should_skip_report(request: Request) -> bool:
    path = request.url.path
    return any(path.startswith(p) for p in _ERROR_REPORT_SKIP_PATHS)


def _request_context(request: Request, status_code: int) -> dict:
    return {
        "request_path": request.url.path,
        "request_method": request.method,
        "status_code": status_code,
    }


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Maneja errores de validación de Pydantic con respuesta personalizada."""
    logger.warning(f"Validation error: {exc.errors()}")
    if REPORT_CLIENT_ERRORS and not _should_skip_report(request):
        await areport_error(
            f"Error de validación: {exc.errors()}",
            f"api:validation {request.method} {request.url.path}",
            error_type="RequestValidationError",
            context=_request_context(request, 422),
            severity="warning",
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Error de validación",
            "errors": exc.errors()
        }
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Registra las HTTPException relevantes y conserva la respuesta estándar."""
    is_server_error = exc.status_code >= 500
    # 401/404 son ruido de fondo (tokens expirados, escaneo de bots): se omiten
    # salvo que se trate de un 5xx.
    noisy_client_error = exc.status_code in (401, 404)
    should_report = not _should_skip_report(request) and (
        is_server_error
        or (REPORT_CLIENT_ERRORS and exc.status_code >= 400 and not noisy_client_error)
    )
    if should_report:
        if is_server_error:
            logger.error(f"HTTP {exc.status_code} en {request.url.path}: {exc.detail}")
        await areport_error(
            f"HTTP {exc.status_code}: {exc.detail}",
            f"api:{request.method} {request.url.path}",
            error_type=f"HTTPException{exc.status_code}",
            exc=exc,
            context=_request_context(request, exc.status_code),
            severity="critical" if is_server_error else "warning",
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


# Manejador global de excepciones
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Maneja excepciones no capturadas."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    if not _should_skip_report(request):
        await areport_error(
            str(exc) or type(exc).__name__,
            f"api:{request.method} {request.url.path}",
            error_type=type(exc).__name__,
            exc=exc,
            context=_request_context(request, 500),
            severity="critical",
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Error interno del servidor"
        }
    )


# ============================================================================
# Endpoints de sistema (sin prefijo de dominio)
# ============================================================================
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Endpoint de health check para monitoreo.
    Retorna el estado de la API.
    """
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


@app.get("/system/readiness", tags=["Health"])
async def readiness_check():
    """
    Verifica dependencias externas que /health no comprueba (hoy: MinIO) - separado
    de /health para no ampliar el radio de un blip transitorio al healthcheck de
    Docker/Caddy. Ver RF-008, spec 002.
    """
    minio_ok = storage_service.check_connection()
    ready = minio_ok
    return JSONResponse(
        content={"status": "ready" if ready else "not_ready", "checks": {"minio": minio_ok}},
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Endpoint raíz con información de la API."""
    return {
        "message": "MCP Tools API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health"
    }


# ============================================================================
# Routers — un módulo por dominio funcional
# ============================================================================
app.include_router(auth_enhanced.router)
app.include_router(career_identity.router)
app.include_router(career_search.router)
app.include_router(job_discovery.router)
app.include_router(career_digital.router)
app.include_router(career_support.router)
app.include_router(career_metrics.router)
app.include_router(career_methodologies.router)
app.include_router(bedrock.router)
app.include_router(bedrock_tasks.router)
app.include_router(notifications.router)
app.include_router(admin_sections.router)
app.include_router(pdf_templates.router)
app.include_router(pdf_template_styles.router)
app.include_router(files.router)
app.include_router(linkedin.router)
app.include_router(public.router)
app.include_router(error_reports.router)


# ============================================================================
# Log de arranque (import-time, antes del primer request)
# ============================================================================
logger.info(f"{settings.APP_NAME} v{settings.APP_VERSION} initialized")
logger.info(f"CORS enabled for origins: {settings.CORS_ORIGINS}")
