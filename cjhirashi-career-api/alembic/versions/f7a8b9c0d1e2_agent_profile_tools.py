"""bedrock_agent_profile_tools — per-agent tool overrides

Revision ID: f7a8b9c0d1e2
Revises: e1f2a3b4c5d6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("bedrock_agent_profile_tools"):
        return
    op.create_table(
        "bedrock_agent_profile_tools",
        sa.Column("profile_id", sa.String(50), nullable=False),
        sa.Column("tool_names", JSONB(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("profile_id"),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("bedrock_agent_profile_tools"):
        op.drop_table("bedrock_agent_profile_tools")
