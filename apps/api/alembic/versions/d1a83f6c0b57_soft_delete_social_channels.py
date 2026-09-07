"""soft delete for social channels

Lets a user remove a channel from their list without destroying anything.

A row delete is not an option here: campaign_targets, publications and
stat_post_metrics all reference social_channels with ON DELETE CASCADE, so
dropping the row would take the record of every post ever published on that
client's real profile with it. The history has to survive the channel.

Revision ID: d1a83f6c0b57
Revises: c9e2b45d7a18
Create Date: 2026-09-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1a83f6c0b57"
down_revision: Union[str, None] = "c9e2b45d7a18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("social_channels", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    # Read on every campaign resolution and on every portal channel listing.
    op.create_index("idx_social_channels_deleted_at", "social_channels", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("idx_social_channels_deleted_at", table_name="social_channels")
    op.drop_column("social_channels", "deleted_at")
