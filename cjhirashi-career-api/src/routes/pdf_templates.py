"""
CRUD de plantillas PDF (tabla pdf_output_templates) y endpoint de render.
El agente agent_pdf_design escribe las mismas filas con la tool `pdf_template`.
"""
# ============================================================================
# Imports
# ============================================================================
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import get_current_user
from models.pdf_output_template import PdfOutputTemplate
from models.pdf_template_style import PdfTemplateStyle
from models.user import User
from repositories.career_repository import CareerRepository
from routes.career_common import register_resource
from schemas.pdf_template import (
    PdfOutputTemplateCreate,
    PdfOutputTemplateResponse,
    PdfOutputTemplateUpdate,
    PdfTemplateRenderRequest,
)
from services.id_generator import normalize_prefixed_id
from services.pdf_service import PDFGeneratorError, generate_html_template_pdf
from services.pdf_template_css import resolve_template_css
from services.pdf_template_render import render_template_html

# ============================================================================
# Router principal y repositorio
# ============================================================================
router = APIRouter(prefix="/pdf-templates", tags=["PDF Templates"])

_repo = CareerRepository(PdfOutputTemplate, resource_key="pdf-output-templates", vectorize=False)
_style_repo = CareerRepository(PdfTemplateStyle, resource_key="pdf-template-styles", vectorize=False)
register_resource("pdf-output-templates", PdfOutputTemplate, vectorize=False)
register_resource("pdf-template-styles", PdfTemplateStyle, vectorize=False)


async def _normalize_style_id(
    db: AsyncSession, user_id: str, style_id: str | None
) -> str | None:
    if style_id is None or style_id == "":
        return None
    normalized = normalize_prefixed_id("pdf_template_styles", style_id)
    style = await _style_repo.get_for_user(db, user_id, normalized)
    if style is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid style_id")
    return normalized


# ============================================================================
# Endpoints CRUD de plantillas
# ============================================================================
@router.get("", response_model=list[PdfOutputTemplateResponse])
async def list_templates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    document_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await _repo.list_for_user(db, current_user.id, skip=skip, limit=limit)
    if document_type:
        items = [i for i in items if i.document_type == document_type]
    return items


@router.get("/defaults/by-type", response_model=PdfOutputTemplateResponse)
async def get_default_template(
    document_type: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PdfOutputTemplate).where(
            PdfOutputTemplate.user_id == current_user.id,
            PdfOutputTemplate.document_type == document_type,
            PdfOutputTemplate.is_default.is_(True),
            PdfOutputTemplate.is_active.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No default template for this type")
    return row


@router.get("/{template_id}", response_model=PdfOutputTemplateResponse)
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _repo.get_for_user(db, current_user.id, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return row


@router.post("", response_model=PdfOutputTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: PdfOutputTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump()
    data["style_id"] = await _normalize_style_id(db, current_user.id, data.get("style_id"))
    return await _repo.create_for_user(db, current_user.id, data)


@router.put("/{template_id}", response_model=PdfOutputTemplateResponse)
async def update_template(
    template_id: str,
    payload: PdfOutputTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _repo.get_for_user(db, current_user.id, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    data = payload.model_dump(exclude_unset=True)
    if "style_id" in data:
        data["style_id"] = await _normalize_style_id(db, current_user.id, data.get("style_id"))
    for k, v in data.items():
        if hasattr(row, k):
            setattr(row, k, v)
    row.version = (row.version or 1) + 1
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await _repo.delete_for_user(db, current_user.id, template_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")


# ============================================================================
# Endpoint: render preview (PDF desde plantilla almacenada)
# ============================================================================
@router.post("/{template_id}/render", summary="Render PDF from stored HTML template")
async def render_pdf_template(
    template_id: str,
    payload: PdfTemplateRenderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _repo.get_for_user(db, current_user.id, template_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    html = render_template_html(row.html_template, payload.variables or {})
    title = payload.title or row.title
    css_content = await resolve_template_css(db, row)
    try:
        pdf_bytes = await generate_html_template_pdf(title=title, html_body=html, css_content=css_content)
    except PDFGeneratorError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    safe = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip()).strip("-") or "document"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}.pdf"'},
    )
