"""
Generic repository for the career-domain (v2) tables.

All 30 career-domain tables share the same shape of concern: every row
belongs to exactly one user (`user_id` column) and must never be
readable/writable by another user. Rather than duplicating that
row-level-isolation logic 30 times, this generic repository implements it
once and is parametrized by the SQLAlchemy model.
"""
import asyncio
import logging
from typing import Generic, Optional, Sequence, Type, TypeVar

from sqlalchemy import Boolean as SABoolean, String, Text, func as sa_func, inspect, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import Base

# ============================================================================
# Imports y tipos genéricos
# ============================================================================

ModelType = TypeVar("ModelType", bound=Base)

logger = logging.getLogger(__name__)

# Fields accepted on the API payload that are not columns of the SQLAlchemy
# model. work-history.achievement_ids syncs Achievement.work_history_id.
# agent-tasks.subtasks crea/actualiza/borra filas hijas (ADR-016).
_VIRTUAL_FIELDS = {
    "work-history": frozenset({"achievement_ids"}),
    "agent-tasks": frozenset({"subtasks"}),
}

# ============================================================================
# Utilidades — tareas en segundo plano
# ============================================================================

# Keeps a strong reference to fire-and-forget indexing tasks so they aren't
# garbage-collected mid-flight (a well-known asyncio.create_task gotcha) -
# self-removes once each task finishes, so this set never actually grows.
_background_tasks: set = set()


def _fire_and_forget(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# ============================================================================
# Repositorio de carrera — CRUD con aislamiento por usuario
# ============================================================================

class CareerRepository(Generic[ModelType]):
    """Generic CRUD repository enforcing per-user row-level isolation."""

    def __init__(self, model: Type[ModelType], resource_key: Optional[str] = None, vectorize: bool = True):
        self.model = model
        # The router-prefix form of the resource (e.g. "operational-methodologies",
        # hyphenated - matches the frontend's CAREER_RESOURCES keys and what
        # Agent Bedrock's tools use), not `model.__tablename__` (underscored).
        # Only set by `build_crud_router`; without it, indexing is skipped.
        self.resource_key = resource_key
        # False for PDF-content tables (e.g. `cv_versions`) - Carlos wants
        # the agent to read those straight from Postgres, never copied into
        # the Qdrant knowledge base. See `build_crud_router`'s `vectorize`
        # param, which is what actually sets this per resource.
        self.vectorize = vectorize
        # Computed once per model (not per request): every real column name
        # (for validating `sort_by`) and the string/text ones among them
        # (for the free-text `search` filter below).
        column_attrs = list(inspect(model).mapper.column_attrs)
        self._column_names = {attr.key for attr in column_attrs}
        self._text_columns = [
            attr.key for attr in column_attrs if isinstance(attr.columns[0].type, (String, Text))
        ]
        self._indexable_columns = [c for c in self._column_names if c not in ("id", "user_id")]
        # NOT NULL columns with no Python-side or server-side default: create_for_user
        # must receive these or Postgres rejects the INSERT. Computed once so
        # _invalid_fields_error can reject a missing one before it ever reaches the
        # DB, same as it already does for unknown field names.
        self._required_columns = sorted(
            attr.key
            for attr in column_attrs
            if attr.key not in ("id", "user_id")
            and not attr.columns[0].nullable
            and attr.columns[0].default is None
            and attr.columns[0].server_default is None
        )

    def _eager_options(self):
        rel = getattr(self.model, "linked_achievements", None)
        if rel is None:
            return []
        return [selectinload(rel)]

    def _pop_virtual_fields(self, data: dict) -> dict:
        virtual = _VIRTUAL_FIELDS.get(self.resource_key or "", frozenset())
        return {key: data.pop(key) for key in list(data) if key in virtual}

    # ------------------------------------------------------------------------
    # Consultas — listado, conteo y obtención
    # ------------------------------------------------------------------------

    def _apply_search(self, stmt, search: Optional[str]):
        if search and self._text_columns:
            like = f"%{search}%"
            stmt = stmt.where(or_(*(getattr(self.model, col).ilike(like) for col in self._text_columns)))
        return stmt

    def _apply_filters(self, stmt, filters: Optional[dict]):
        """AND equality / membership filters. Unknown keys are ignored."""
        if not filters:
            return stmt
        for field, raw in filters.items():
            if field not in self._column_names or field in ("id", "user_id"):
                continue
            column = getattr(self.model, field)
            values = raw if isinstance(raw, list) else [raw]
            values = [item for item in values if item is not None and item != ""]
            if not values:
                continue
            col_type = column.type
            if isinstance(col_type, SABoolean):
                wanted = [self._as_bool(item) for item in values]
                wanted = [item for item in wanted if item is not None]
                if not wanted:
                    continue
                stmt = stmt.where(column.in_(wanted) if len(wanted) > 1 else column.is_(wanted[0]))
            elif isinstance(col_type, JSONB):
                stmt = stmt.where(or_(*(column.contains([str(item)]) for item in values)))
            elif len(values) == 1:
                stmt = stmt.where(column == values[0])
            else:
                stmt = stmt.where(column.in_([str(item) for item in values]))
        return stmt

    @staticmethod
    def _as_bool(value) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "1", "yes", "si", "sí"):
                return True
            if lowered in ("false", "0", "no"):
                return False
        return None

    async def list_for_user(
        self,
        db: AsyncSession,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
        sort_by: Optional[str] = None,
        sort_dir: str = "asc",
        search: Optional[str] = None,
        filters: Optional[dict] = None,
    ) -> Sequence[ModelType]:
        """Return a page of rows belonging to `user_id`.

        `sort_by` defaults to newest-first (`id desc`) when absent or not a
        real column on this model - never trusted blindly, since it comes
        straight from the query string. `search` does a case-insensitive
        OR-match across every string/text column of the model. `filters` is
        an optional {column: value | [values]} map for categorized fields.
        """
        stmt = select(self.model).options(*self._eager_options()).where(self.model.user_id == user_id)
        stmt = self._apply_search(stmt, search)
        stmt = self._apply_filters(stmt, filters)

        if sort_by and sort_by in self._column_names:
            column = getattr(self.model, sort_by)
            stmt = stmt.order_by(column.desc() if sort_dir == "desc" else column.asc())
        else:
            stmt = stmt.order_by(self.model.id.desc())

        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def count_for_user(
        self,
        db: AsyncSession,
        user_id: str,
        search: Optional[str] = None,
        filters: Optional[dict] = None,
    ) -> int:
        """Return the number of rows belonging to `user_id`, with the same
        search/filters as the list endpoint so pagination stays accurate."""
        stmt = select(sa_func.count()).select_from(self.model).where(self.model.user_id == user_id)
        stmt = self._apply_search(stmt, search)
        stmt = self._apply_filters(stmt, filters)
        result = await db.execute(stmt)
        return result.scalar_one()

    def is_distinct_field(self, field: str) -> bool:
        """True when `field` is a string/text column that may back a creatable select."""
        return field in self._text_columns and field not in ("id", "user_id")

    async def distinct_values_for_user(
        self, db: AsyncSession, user_id: str, field: str
    ) -> list[str]:
        """Unique non-empty values of a text column for `user_id`, sorted.

        Powers creatable selects: options already saved on other rows reappear
        as listed choices; a newly typed value is stored on the record and
        shows up here on the next load.
        """
        if not self.is_distinct_field(field):
            raise ValueError(f"Field {field!r} is not a text column on this resource")
        column = getattr(self.model, field)
        stmt = (
            select(column)
            .where(self.model.user_id == user_id, column.is_not(None), column != "")
            .distinct()
            .order_by(column.asc())
            .limit(500)
        )
        result = await db.execute(stmt)
        values: list[str] = []
        seen: set[str] = set()
        for raw in result.scalars().all():
            text = str(raw).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            values.append(text)
        return values

    async def get_for_user(
        self, db: AsyncSession, user_id: str, item_id: str
    ) -> Optional[ModelType]:
        """Fetch a single row by id, scoped to `user_id`. Never trusts a bare id lookup."""
        stmt = select(self.model).options(*self._eager_options()).where(
            self.model.id == item_id, self.model.user_id == user_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------------
    # Mutaciones — creación, actualización y eliminación
    # ------------------------------------------------------------------------

    async def create_for_user(
        self, db: AsyncSession, user_id: str, data: dict
    ) -> ModelType:
        """
        Create a row, forcing `user_id` from the authenticated user (never
        from payload).

        Commits explicitly rather than relying on `database.get_db()`'s
        post-response commit: that commit runs *after* the HTTP response has
        already been sent to the client (it fires when the dependency's
        AsyncExitStack is closed, which happens outside the ASGI `send()`
        call), so a client issuing an immediate follow-up request can race
        the commit and see stale/missing data. Explicit commit here
        guarantees the write is durable before the response is returned.
        """
        data = dict(data)
        data.pop("user_id", None)
        virtual = self._pop_virtual_fields(data)
        if self.resource_key == "agent-tasks":
            await self._validate_task_parent(db, user_id, data.get("parent_id"))
        if self.resource_key == "projects" and "competency_ids" in data:
            data["competency_ids"] = await self._resolve_competency_ids(
                db, user_id, data.get("competency_ids")
            )
        obj = self.model(user_id=user_id, **data)
        db.add(obj)
        await db.flush()
        await self._apply_virtual_fields(db, user_id, obj, virtual)
        await db.commit()
        loaded = await self._reload_after_write(db, user_id, obj.id, virtual)
        _fire_and_forget(self._index_for_search(loaded or obj, user_id))
        return loaded or obj

    async def update_for_user(
        self, db: AsyncSession, user_id: str, item_id: str, data: dict
    ) -> Optional[ModelType]:
        """Partially update a row scoped to `user_id`. Returns None if not found/not owned."""
        obj = await self.get_for_user(db, user_id, item_id)
        if obj is None:
            return None
        data = dict(data)
        data.pop("user_id", None)
        virtual = self._pop_virtual_fields(data)
        if self.resource_key == "agent-tasks" and "parent_id" in data:
            await self._validate_task_parent(db, user_id, data.get("parent_id"), item_id)
        if self.resource_key == "projects" and "competency_ids" in data:
            data["competency_ids"] = await self._resolve_competency_ids(
                db, user_id, data.get("competency_ids")
            )
        for key, value in data.items():
            setattr(obj, key, value)
        await db.flush()
        await self._apply_virtual_fields(db, user_id, obj, virtual)
        await db.commit()
        loaded = await self._reload_after_write(db, user_id, item_id, virtual)
        _fire_and_forget(self._index_for_search(loaded or obj, user_id))
        return loaded or obj

    async def delete_for_user(self, db: AsyncSession, user_id: str, item_id: str) -> bool:
        """Delete a row scoped to `user_id`. Returns False if not found/not owned."""
        obj = await self.get_for_user(db, user_id, item_id)
        if obj is None:
            return False
        await db.delete(obj)
        await db.commit()
        _fire_and_forget(self._remove_from_search(item_id))
        return True

    async def _reload_after_write(
        self, db: AsyncSession, user_id: str, item_id: str, virtual: dict
    ) -> Optional[ModelType]:
        # Core UPDATEs for virtual FKs bypass the identity map; expire so
        # selectinload sees the new Achievement.work_history_id values.
        if virtual:
            db.expire_all()
        return await self.get_for_user(db, user_id, item_id)

    async def _validate_task_parent(
        self, db: AsyncSession, user_id: str, parent_id: Optional[str], self_id: Optional[str] = None
    ) -> None:
        if not parent_id:
            return
        if self_id and parent_id == self_id:
            raise ValueError("una tarea no puede ser padre de sí misma")
        from models.bedrock_task import BedrockTask

        parent = await db.get(BedrockTask, parent_id)
        if parent is None or parent.user_id != user_id:
            raise ValueError("parent_id no existe o no es tuyo")
        if parent.parent_id:
            raise ValueError("las subtareas no pueden tener subtareas")

    async def _resolve_competency_ids(
        self, db: AsyncSession, user_id: str, raw_ids: Optional[list]
    ) -> list[str]:
        """Turn `projects.competency_ids` input into real `competencies` ids.

        Each entry is either an existing competency id, an existing
        competency name (case-insensitive - avoids "FastAPI"/"fastapi"
        duplicates), or a brand-new technology name typed in the admin's
        creatable multi-select, which gets created here as
        `type="technical"`. Keeps input order, drops duplicates/blanks.
        """
        if not raw_ids:
            return []
        from models.competencies import Competency

        result = await db.execute(
            select(Competency.id, Competency.name).where(Competency.user_id == user_id)
        )
        by_id = {}
        by_name = {}
        for comp_id, name in result.all():
            by_id[comp_id] = comp_id
            by_name[name.lower()] = comp_id

        resolved: list[str] = []
        seen: set[str] = set()
        for raw in raw_ids:
            text = str(raw).strip()
            if not text:
                continue
            comp_id = by_id.get(text) or by_name.get(text.lower())
            if comp_id is None:
                new_comp = Competency(user_id=user_id, name=text, type="technical")
                db.add(new_comp)
                await db.flush()
                comp_id = new_comp.id
                by_id[comp_id] = comp_id
                by_name[text.lower()] = comp_id
            if comp_id not in seen:
                seen.add(comp_id)
                resolved.append(comp_id)
        return resolved

    async def _apply_virtual_fields(
        self, db: AsyncSession, user_id: str, obj: ModelType, virtual: dict
    ) -> None:
        if "achievement_ids" in virtual:
            from models.achievement import Achievement

            wanted = [str(item_id) for item_id in (virtual["achievement_ids"] or []) if item_id]
            await db.execute(
                update(Achievement)
                .where(
                    Achievement.user_id == user_id,
                    Achievement.work_history_id == obj.id,
                    *([Achievement.id.notin_(wanted)] if wanted else []),
                )
                .values(work_history_id=None)
            )
            if wanted:
                await db.execute(
                    update(Achievement)
                    .where(Achievement.user_id == user_id, Achievement.id.in_(wanted))
                    .values(work_history_id=obj.id)
                )
        if "subtasks" in virtual:
            await self._sync_subtasks(db, user_id, obj, virtual.get("subtasks") or [])

    async def _sync_subtasks(self, db: AsyncSession, user_id: str, parent, items: list) -> None:
        from models.bedrock_task import BedrockTask
        from schemas.bedrock_task import SubtaskInput

        if getattr(parent, "parent_id", None):
            raise ValueError("las subtareas no pueden tener subtareas")
        result = await db.execute(
            select(BedrockTask).where(BedrockTask.user_id == user_id, BedrockTask.parent_id == parent.id)
        )
        existing = {child.id: child for child in result.scalars().all()}
        keep: set[str] = set()
        for index, raw in enumerate(items):
            payload = raw if isinstance(raw, dict) else raw.model_dump()
            payload = {**payload, "parent_id": parent.id, "sort_order": index}
            payload.pop("subtasks", None)
            parsed = SubtaskInput.model_validate(payload)
            data = parsed.model_dump(exclude={"id", "subtasks"})
            data["parent_id"] = parent.id
            data["sort_order"] = index
            child_id = parsed.id
            if child_id and child_id in existing:
                child = existing[child_id]
                for key, value in data.items():
                    setattr(child, key, value)
                keep.add(child_id)
            else:
                child = BedrockTask(user_id=user_id, **data)
                db.add(child)
                await db.flush()
                keep.add(child.id)
        for child_id, child in existing.items():
            if child_id not in keep:
                await db.delete(child)


    # ------------------------------------------------------------------------
    # Indexación vectorial — búsqueda semántica (Qdrant)
    # ------------------------------------------------------------------------

    def _record_to_text(self, obj: ModelType) -> str:
        """Flatten a record into `column: value` lines for embedding - every
        column except `id`/`user_id`, skipping empty values."""
        lines = []
        for col in self._indexable_columns:
            value = getattr(obj, col, None)
            if value not in (None, "", []):
                lines.append(f"{col}: {value}")
        return "\n".join(lines)

    def _legacy_record_id(self, record_id) -> Optional[str]:
        """The pre-migration bare-integer id for this record, or None.

        Ids used to be bare integers (`33`) and were migrated to a prefixed
        form (`opm-33`). The old Qdrant point sits under a different
        `_point_id`; `upsert_point` uses this to delete that twin (spec 003
        RF-013). Returns None when `record_id` has no known prefix or isn't
        the `{prefix}-{int}` shape."""
        from services.id_generator import prefix_for_key

        if not self.resource_key or not isinstance(record_id, str):
            return None
        prefix = prefix_for_key(self.resource_key)
        if not prefix:
            return None
        head = f"{prefix}-"
        if record_id.startswith(head):
            tail = record_id[len(head):]
            if tail.isdigit():
                return tail
        return None

    async def reindex_for_user(self, db: AsyncSession, user_id: str) -> int:
        """Re-embed and re-upsert every live row of this resource for
        `user_id` into Qdrant, in pages (never one big SELECT). Awaits each
        index call - unlike the fire-and-forget hook on writes - so the
        caller (`services.bedrock.knowledge_base.reindex_knowledge_base`)
        knows when it's done. Returns the number of rows reindexed. A no-op
        for resources without a `resource_key` or with `vectorize=False`."""
        if not self.resource_key or not self.vectorize:
            return 0
        from services import qdrant_service

        total = 0
        seen_ids: list = []
        skip = 0
        batch = 100
        while True:
            rows = await self.list_for_user(db, user_id, skip=skip, limit=batch)
            if not rows:
                break
            for row in rows:
                await self._index_for_search(row, user_id)
                seen_ids.append(row.id)
                total += 1
            if len(rows) < batch:
                break
            skip += batch
        # Rebuild semantics: drop points for rows that no longer exist in PG
        # (deleted rows whose best-effort delete hook never reached Qdrant).
        await qdrant_service.prune_stale_points(user_id, self.resource_key, seen_ids)
        return total

    async def _index_for_search(self, obj: ModelType, user_id: str) -> None:
        """Best-effort: (re)index this record in Qdrant for Agent Bedrock's
        knowledge base. Never lets an indexing failure fail the real write -
        logs and moves on. Skipped entirely if this repository wasn't built
        with a `resource_key` (see `build_crud_router`), or if `vectorize`
        is False for this resource (PDF-content tables - the agent reads
        those straight from Postgres instead)."""
        if not self.resource_key or not self.vectorize:
            return
        try:
            from services import bedrock_service, qdrant_service

            text = self._record_to_text(obj)
            if not text:
                return
            vector = await bedrock_service.embed_text(text)
            resource_type = "methodology" if self.resource_key == "operational-methodologies" else "career_record"
            extra_payload = None
            if resource_type == "methodology":
                # `title`/`section` en el payload → `search type=methodology`
                # arma extractos sin re-parsear el markdown (spec 003 RF-016).
                extra_payload = {
                    "agent_profile_ids": getattr(obj, "agent_profile_ids", None) or [],
                    "title": getattr(obj, "title", None),
                    "section": getattr(obj, "section", None),
                }
            await qdrant_service.upsert_point(
                user_id=user_id,
                resource_type=resource_type,
                resource_key=self.resource_key,
                record_id=obj.id,
                text=text,
                vector=vector,
                extra_payload=extra_payload,
                legacy_record_id=self._legacy_record_id(obj.id),
            )
        except Exception as exc:
            logger.warning(
                "Bedrock knowledge-base indexing failed for %s#%s - continuing without it",
                self.resource_key,
                getattr(obj, "id", "?"),
                exc_info=True,
            )
            from services.error_reporting import report_error

            report_error(
                str(exc) or "Fallo al indexar en la base de conocimiento",
                "repository:career_repository.index_for_search",
                error_type=type(exc).__name__, exc=exc,
                context={"resource_key": self.resource_key, "record_id": getattr(obj, "id", None)},
                severity="warning",
            )

    async def _remove_from_search(self, item_id: str) -> None:
        """Best-effort counterpart to `_index_for_search`, called after a real delete."""
        if not self.resource_key or not self.vectorize:
            return
        try:
            from services import qdrant_service

            await qdrant_service.delete_point(resource_key=self.resource_key, record_id=item_id)
        except Exception as _cleanup_exc:
            logger.warning(
                "Bedrock knowledge-base cleanup failed for %s#%s - continuing without it",
                self.resource_key,
                item_id,
                exc_info=True,
            )
            from services.error_reporting import report_error

            report_error(
                str(_cleanup_exc) or "Fallo al limpiar la base de conocimiento",
                "repository:career_repository.remove_from_search",
                error_type=type(_cleanup_exc).__name__, exc=_cleanup_exc,
                context={"resource_key": self.resource_key, "record_id": item_id},
                severity="warning",
            )
