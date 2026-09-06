"""add omni_ai_agent_configs.auto_generate_draft

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-10 17:00:00.000000

Additive column, orthogonal to response_mode: controls whether a draft is
generated automatically on every inbound message (default, unchanged
behavior) or only on manual operator request (see
app/models/omnichannel.py::OmniAIAgentConfig.auto_generate_draft docstring).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('omni_ai_agent_configs', sa.Column('auto_generate_draft', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.alter_column('omni_ai_agent_configs', 'auto_generate_draft', server_default=None)


def downgrade() -> None:
    op.drop_column('omni_ai_agent_configs', 'auto_generate_draft')
