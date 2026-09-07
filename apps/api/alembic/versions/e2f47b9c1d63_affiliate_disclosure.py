"""affiliate disclosure on campaigns

An affiliate link makes a post commercial communication: the promoter earns a
commission, whether or not anyone pays them directly. That has to be declared,
and the declaration is the advertiser's responsibility as much as the
promoter's.

The text is written centrally, so the control belongs here rather than with each
collaborator: with hundreds of them, hoping everyone remembers is not a control.

The wording lives in a settings row instead of the code because the exact
formulation is a legal decision - it gets settled once and applies everywhere,
with no deploy and no campaign to re-edit.

Revision ID: e2f47b9c1d63
Revises: d1a83f6c0b57
Create Date: 2026-09-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e2f47b9c1d63"
down_revision: Union[str, None] = "d1a83f6c0b57"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column(
            "include_affiliate_disclosure",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "platform_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("affiliate_disclosure_text", sa.String(length=500), nullable=True),
        sa.Column("affiliate_disclosure_text_short", sa.String(length=120), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
    op.drop_column("campaigns", "include_affiliate_disclosure")
