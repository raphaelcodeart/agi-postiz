"""omnichannel: integrazione CRM Mamify (crm_enabled, chiave cifrata, base url)

Revision ID: a7d3c9e1f5b2
Revises: f2c7a9e3d4b1
Create Date: 2026-10-26
"""
import sqlalchemy as sa

from alembic import op

revision = "a7d3c9e1f5b2"
down_revision = "f2c7a9e3d4b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("omni_ai_agent_configs", sa.Column("crm_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("omni_ai_agent_configs", sa.Column("crm_api_key_encrypted", sa.Text(), nullable=True))
    op.add_column("omni_ai_agent_configs", sa.Column("crm_base_url", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("omni_ai_agent_configs", "crm_base_url")
    op.drop_column("omni_ai_agent_configs", "crm_api_key_encrypted")
    op.drop_column("omni_ai_agent_configs", "crm_enabled")
