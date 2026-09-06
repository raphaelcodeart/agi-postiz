"""block duplicate channels across providers

A user can end up with the same real social account connected twice: once
directly through our provider, once through their Buffer key pasted by an
administrator. Publishing to both would post every campaign twice on the
client's actual profile - the kind of failure a client notices immediately.

The column marks the newcomer as a duplicate of the existing channel; sync keeps
it inactive and the admin API refuses to enable it until the flag is cleared.

Revision ID: c9e2b45d7a18
Revises: b8d5f2a71c04
Create Date: 2026-09-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9e2b45d7a18"
down_revision: Union[str, None] = "b8d5f2a71c04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "social_channels",
        sa.Column("duplicate_of_channel_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_social_channels_duplicate_of",
        "social_channels",
        "social_channels",
        ["duplicate_of_channel_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_social_channels_duplicate_of",
        "social_channels",
        ["duplicate_of_channel_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_social_channels_duplicate_of", table_name="social_channels")
    op.drop_constraint("fk_social_channels_duplicate_of", "social_channels", type_="foreignkey")
    op.drop_column("social_channels", "duplicate_of_channel_id")
