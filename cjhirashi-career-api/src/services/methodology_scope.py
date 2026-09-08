"""Alcance de una metodología operativa a uno o más agentes."""
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.bedrock.agent_profiles import AGENT_METHODOLOGIES


def applies_to_agent(agent_profile_ids: Optional[Any], caller_profile_id: Optional[str]) -> bool:
    """True si la metodología es visible para el agente caller.

    Lista vacía o null = todos. El guardián L2 `agent_methodologies` ve todas.
    """
    if not caller_profile_id or caller_profile_id == AGENT_METHODOLOGIES:
        return True
    ids = agent_profile_ids or []
    if not isinstance(ids, list) or not ids:
        return True
    return caller_profile_id in ids


def is_shared_methodology(agent_profile_ids: Optional[Any]) -> bool:
    """True si la metodología aplica a todos los agentes (lista vacía o null)."""
    ids = agent_profile_ids or []
    return not isinstance(ids, list) or not ids


def next_agent_profile_ids(
    current_ids: Optional[Any],
    profile_id: str,
    should_apply: bool,
    all_profile_ids: set[str],
) -> Optional[List[str]]:
    """Nueva lista `agent_profile_ids`, o None si no hay que persistir.

    Vacío = compartida (todos). Al desasignar el último dueño exclusivo se
    aparca en `agent_methodologies` para no volver a compartirla con el
    agente que se acaba de quitar.
    """
    current = [item for item in (current_ids or []) if item]
    shared = not current
    currently_assigned = shared or profile_id in current
    if currently_assigned == should_apply:
        return None
    if should_apply:
        return current + [profile_id]
    if shared:
        return sorted(all_profile_ids - {profile_id})
    remaining = [item for item in current if item != profile_id]
    if remaining:
        return remaining
    if profile_id != AGENT_METHODOLOGIES:
        return [AGENT_METHODOLOGIES]
    return []


async def list_methodologies_for_catalog(
    db: AsyncSession,
    user_id: str,
    caller_profile_id: str,
) -> List[Dict[str, Any]]:
    """Todas las metodologías del usuario, con flag de asignación al caller."""
    from models.operational_methodology import OperationalMethodology

    result = await db.execute(
        select(
            OperationalMethodology.id,
            OperationalMethodology.title,
            OperationalMethodology.section,
            OperationalMethodology.agent_profile_ids,
        )
        .where(OperationalMethodology.user_id == user_id)
        .order_by(OperationalMethodology.title.asc())
    )
    items: List[Dict[str, Any]] = []
    for row in result.all():
        shared = is_shared_methodology(row.agent_profile_ids)
        ids = row.agent_profile_ids or []
        assigned = shared or (isinstance(ids, list) and caller_profile_id in ids)
        items.append(
            {
                "id": row.id,
                "title": row.title,
                "section": row.section,
                "shared": shared,
                "assigned": assigned,
            }
        )
    return items


async def set_agent_methodologies(
    db: AsyncSession,
    user_id: str,
    profile_id: str,
    methodology_ids: List[str],
) -> List[Dict[str, Any]]:
    """Asigna al agente exactamente las metodologías de `methodology_ids`."""
    from models.operational_methodology import OperationalMethodology
    from repositories.career_repository import CareerRepository
    from services.bedrock.agent_profiles import get_profile, known_agent_profile_ids

    profile_id = get_profile(profile_id).id

    wanted = set(methodology_ids)
    all_ids = known_agent_profile_ids()
    result = await db.execute(
        select(OperationalMethodology).where(OperationalMethodology.user_id == user_id)
    )
    repo = CareerRepository(
        OperationalMethodology,
        resource_key="operational-methodologies",
        vectorize=True,
    )
    for row in result.scalars().all():
        nxt = next_agent_profile_ids(
            row.agent_profile_ids,
            profile_id,
            row.id in wanted,
            all_ids,
        )
        if nxt is None:
            continue
        await repo.update_for_user(db, user_id, row.id, {"agent_profile_ids": nxt})
    # Re-index EVERY methodology of this user in Qdrant, awaited, even when no
    # `agent_profile_ids` changed above. The catalog injected into the prompt
    # reads straight from Postgres and was already correct; the bug (spec 003
    # reopening, RF-014) is that `search_knowledge_base type=methodology` reads
    # Qdrant, whose index drifted. Forcing the re-index here makes every save
    # from the agent catalog self-heal the vector store.
    await repo.reindex_for_user(db, user_id)
    return await list_methodologies_for_catalog(db, user_id, profile_id)


async def list_assigned_methodologies(
    db: AsyncSession,
    user_id: str,
    caller_profile_id: str,
) -> List[Dict[str, Any]]:
    """Catálogo de metodologías que el caller debe consultar.

    Fuente de verdad: `agent_profile_ids` en Admin Panel, no secciones hardcoded.
    Una metodología nueva asignada al agente aparece aquí en el siguiente turno.
    """
    from models.operational_methodology import OperationalMethodology

    result = await db.execute(
        select(
            OperationalMethodology.id,
            OperationalMethodology.title,
            OperationalMethodology.section,
            OperationalMethodology.agent_profile_ids,
        )
        .where(OperationalMethodology.user_id == user_id)
        .order_by(OperationalMethodology.title.asc())
    )
    assigned: List[Dict[str, Any]] = []
    for row in result.all():
        if applies_to_agent(row.agent_profile_ids, caller_profile_id):
            assigned.append(
                {
                    "id": row.id,
                    "title": row.title,
                    "section": row.section,
                    "shared": is_shared_methodology(row.agent_profile_ids),
                }
            )
    return assigned
