"""
Generic CRUD router factory for the career-domain (v2) tables.

Builds a standard `GET list / GET by id / POST / PUT / DELETE` APIRouter
for a given (model, schemas) tuple. Every endpoint requires JWT
authentication and enforces row-level user isolation via
`repositories.career_repository.CareerRepository` - the `user_id` is
always taken from the authenticated user, never from the request body or
query string.
"""
# ============================================================================
# Imports
# ============================================================================
from typing import Dict, List, Optional, Type, Callable, Any
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import Base, get_db
from middleware.auth import get_current_user
from models.user import User
from repositories.career_repository import CareerRepository

# ============================================================================
# Registro de recursos (RESOURCE_REGISTRY)
# ============================================================================
# resource_key -> SQLAlchemy model, populated automatically below as each
# `build_crud_router(...)` call registers itself - never maintained by hand.
# This is what lets Agent Bedrock's tools (services/bedrock_service.py)
# operate any of the ~30 career-domain resources generically, the same way
# CareerResourceView.tsx's CAREER_RESOURCES does on the frontend.
RESOURCE_REGISTRY: Dict[str, Type[Base]] = {}

# resource_key -> whether this resource is indexed in Agent Bedrock's Qdrant
# knowledge base. Populated alongside RESOURCE_REGISTRY (by `build_crud_router`
# and by the few sites that build a `CareerRepository` by hand). Single source
# of truth for "what gets reindexed" - never hand-maintain a separate list.
# Absent key defaults to True (the `build_crud_router` default).
RESOURCE_VECTORIZE: Dict[str, bool] = {}


def register_resource(resource_key: str, model: Type[Base], *, vectorize: bool = True) -> None:
    """Register a career resource and its knowledge-base indexing flag.

    Called by `build_crud_router` and by the manual `CareerRepository`
    construction sites (`cv-versions`, `pdf-*`) so `RESOURCE_VECTORIZE`
    always mirrors `RESOURCE_REGISTRY`.
    """
    RESOURCE_REGISTRY[resource_key] = model
    RESOURCE_VECTORIZE[resource_key] = vectorize


# ============================================================================
# Factory: build_crud_router
# ============================================================================
def build_crud_router(
    *,
    prefix: str,
    tags: List[str],
    model: Type[Base],
    create_schema: Type[BaseModel],
    update_schema: Type[BaseModel],
    response_schema: Type[BaseModel],
    entity_name: str,
    vectorize: bool = True,
    after_write: Optional[Callable[[Any], None]] = None,
) -> APIRouter:
    """Create an APIRouter with standard CRUD endpoints for `model`.

    `vectorize=False` opts this resource out of the Qdrant knowledge-base
    indexing that otherwise happens automatically on every write (see
    `CareerRepository._index_for_search`) - use it for PDF-content tables
    (e.g. `cv-versions`): the agent should read those straight from
    Postgres, never from a copy in the vector store.
    """
    router = APIRouter(prefix=prefix, tags=tags)
    resource_key = prefix.lstrip("/")
    repository: CareerRepository = CareerRepository(model, resource_key=resource_key, vectorize=vectorize)
    register_resource(resource_key, model, vectorize=vectorize)

    class CountResponse(BaseModel):
        count: int

    class DistinctValuesResponse(BaseModel):
        field: str
        values: List[str]

    def _parse_filters(raw: Optional[str]) -> Optional[dict]:
        if not raw or not raw.strip():
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="filters must be a JSON object",
            ) from exc
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="filters must be a JSON object",
            )
        return parsed

    # ============================================================================
    # Endpoints CRUD estándar (list / count / get / create / update / delete)
    # ============================================================================

    @router.get("", response_model=List[response_schema], summary=f"List {entity_name}")
    async def list_items(
        skip: int = Query(0, ge=0, description="Pagination offset"),
        limit: int = Query(20, ge=1, le=100, description="Page size"),
        sort_by: Optional[str] = Query(None, description="Column name to sort by"),
        sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
        search: Optional[str] = Query(None, description="Case-insensitive search across text columns"),
        filters: Optional[str] = Query(None, description="JSON object of column filters"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        return await repository.list_for_user(
            db,
            current_user.id,
            skip=skip,
            limit=limit,
            sort_by=sort_by,
            sort_dir=sort_dir,
            search=search,
            filters=_parse_filters(filters),
        )

    # Declared before "/{item_id}" - a path-param route would otherwise catch
    # "/count" as if item_id="count".
    @router.get("/count", response_model=CountResponse, summary=f"Count {entity_name}")
    async def count_items(
        search: Optional[str] = Query(None, description="Same search as the list endpoint"),
        filters: Optional[str] = Query(None, description="Same JSON filters as the list endpoint"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        count = await repository.count_for_user(
            db, current_user.id, search=search, filters=_parse_filters(filters)
        )
        return CountResponse(count=count)

    # Declared before "/{item_id}" so "distinct" is not parsed as an id.
    @router.get(
        "/distinct/{field}",
        response_model=DistinctValuesResponse,
        summary=f"Distinct {entity_name} values for a text column",
    )
    async def distinct_values(
        field: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        if not repository.is_distinct_field(field):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field!r} is not a text column on {entity_name}",
            )
        values = await repository.distinct_values_for_user(db, current_user.id, field)
        return DistinctValuesResponse(field=field, values=values)

    @router.get(
        "/{item_id}", response_model=response_schema, summary=f"Get a single {entity_name}"
    )
    async def get_item(
        item_id: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        obj = await repository.get_for_user(db, current_user.id, item_id)
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{entity_name} not found"
            )
        return obj

    @router.post(
        "",
        response_model=response_schema,
        status_code=status.HTTP_201_CREATED,
        summary=f"Create a {entity_name}",
    )
    async def create_item(
        payload: create_schema,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        try:
            obj = await repository.create_for_user(db, current_user.id, payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if after_write:
            after_write(obj)
        return obj

    @router.put(
        "/{item_id}", response_model=response_schema, summary=f"Update a {entity_name}"
    )
    async def update_item(
        item_id: str,
        payload: update_schema,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        data = payload.model_dump(exclude_unset=True)
        try:
            obj = await repository.update_for_user(db, current_user.id, item_id, data)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{entity_name} not found"
            )
        if after_write:
            after_write(obj)
        return obj

    @router.delete(
        "/{item_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary=f"Delete a {entity_name}",
    )
    async def delete_item(
        item_id: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        obj = await repository.get_for_user(db, current_user.id, item_id)
        parent_id = getattr(obj, "parent_id", None) if obj is not None else None
        deleted = await repository.delete_for_user(db, current_user.id, item_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{entity_name} not found"
            )
        if after_write:
            after_write(type("Deleted", (), {"id": item_id, "parent_id": parent_id})())

    return router
