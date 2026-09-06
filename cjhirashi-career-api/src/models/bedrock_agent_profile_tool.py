"""
BedrockAgentProfileTool — override de herramientas por perfil de agente.

Tabla de configuración editable desde Admin Panel. Una fila por perfil
(orchestrator, identity, search, …). `tool_names` en `None` = default de código
(`services/bedrock/profile_tools.py`).
"""
from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database import Base


class BedrockAgentProfileTool(Base):
    """Override del set de herramientas para un perfil concreto."""

    __tablename__ = "bedrock_agent_profile_tools"

    # --- Clave primaria (profile_id coincide con agent_profiles.py) ---
    profile_id = Column(String(50), primary_key=True)

    # --- Contenido editable: set completo de tools (None = default de código) ---
    tool_names = Column(JSONB, nullable=True)

    # --- Auditoría temporal ---
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<BedrockAgentProfileTool(profile_id={self.profile_id!r})>"
