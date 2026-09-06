"""Override de herramientas por perfil (código por defecto ∩ override Admin).

Modelo análogo al prompt suffix (`profile_prompts.py`): el default vive en
`agent_profiles.py` (nivel + `allowed_tool_names`), y el Admin puede reemplazar el
set completo desde el catálogo. `delegate_to_specialist` no es editable — se aplica
por nivel (D-2).
"""
from typing import Dict, List, Optional, Sequence, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bedrock_agent_profile_tool import BedrockAgentProfileTool
from services.bedrock.agent_profiles import AgentProfile, get_profile, tools_for_profile
from services.bedrock import tools as bedrock_tools


def default_tool_names(profile: AgentProfile) -> Set[str]:
    """Set por defecto derivado del código (nivel + allowed_tool_names)."""
    return set(tools_for_profile(profile, bedrock_tools.all_tool_names()))


def effective_tool_names(profile: AgentProfile, override: Optional[Sequence[str]]) -> Set[str]:
    """Override reemplaza el default (D-1); delegate_to_specialist por nivel (D-2)."""
    if override is None:
        names = default_tool_names(profile)
    else:
        names = set(override) & bedrock_tools.all_tool_names()
    if profile.can_delegate:
        names.add("delegate_to_specialist")
    else:
        names.discard("delegate_to_specialist")
    return names


def validate_tool_names(tool_names: Sequence[str]) -> List[str]:
    """Normaliza (ordenado, sin duplicados) y valida contra el catálogo.

    Lanza `ValueError` si algún nombre no existe en `all_tool_names()` (RF-004).
    """
    cleaned = sorted(set(tool_names))
    unknown = set(cleaned) - bedrock_tools.all_tool_names()
    if unknown:
        raise ValueError(f"Unknown tool names: {sorted(unknown)}")
    return cleaned


def list_builtin_tool_catalog() -> List[Dict[str, str]]:
    """Catálogo read-only de tools integradas (name + description) — RF-009."""
    return [
        {"name": tool["name"], "description": tool["description"]}
        for tool in bedrock_tools._RAW_TOOLS
    ]


async def get_tool_override(db: AsyncSession, profile_id: str) -> Optional[List[str]]:
    result = await db.execute(
        select(BedrockAgentProfileTool).where(
            BedrockAgentProfileTool.profile_id == profile_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None or row.tool_names is None:
        return None
    return [str(x) for x in row.tool_names]


async def list_tool_overrides(db: AsyncSession) -> Dict[str, List[str]]:
    """Mapa profile_id → tool_names (solo filas con override presente)."""
    result = await db.execute(select(BedrockAgentProfileTool))
    return {
        row.profile_id: [str(x) for x in row.tool_names]
        for row in result.scalars().all()
        if row.tool_names is not None
    }


async def get_tool_state(db: AsyncSession, profile: AgentProfile) -> Dict[str, object]:
    override = await get_tool_override(db, profile.id)
    defaults = default_tool_names(profile)
    effective = effective_tool_names(profile, override)
    return {
        "profile_id": profile.id,
        "default_tools": sorted(defaults),
        "override_tools": sorted(override) if override is not None else None,
        "effective_tools": sorted(effective),
    }


async def set_tool_override(
    db: AsyncSession,
    profile_id: str,
    tool_names: Optional[Sequence[str]],
) -> Dict[str, object]:
    profile = get_profile(profile_id)
    profile_id = profile.id
    cleaned = validate_tool_names(tool_names) if tool_names is not None else None

    result = await db.execute(
        select(BedrockAgentProfileTool).where(
            BedrockAgentProfileTool.profile_id == profile_id
        )
    )
    row = result.scalar_one_or_none()
    if cleaned is None:
        if row:
            await db.delete(row)
            await db.commit()
    else:
        if row:
            row.tool_names = cleaned
        else:
            db.add(BedrockAgentProfileTool(profile_id=profile_id, tool_names=cleaned))
        await db.commit()
    return await get_tool_state(db, profile)
