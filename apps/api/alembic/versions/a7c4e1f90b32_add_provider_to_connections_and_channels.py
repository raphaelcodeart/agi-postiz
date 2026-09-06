"""add provider to connections and channels

Introduces the multi-provider split: a connection (and, denormalized, a channel)
now records which upstream it publishes through. Existing rows are Buffer, which
is what the server_default encodes - no backfill step is needed, and the columns
are NOT NULL from the start rather than nullable-then-tightened.

The unique constraint replaces an invariant that until now lived only in
application code ("one connection per user", enforced by a .first() lookup).
Widening it to (user_id, provider) is what lets a user hold a Buffer connection
and a direct one at the same time, splitting channels across both.

Revision ID: a7c4e1f90b32
Revises: e5f6a7b8c9d0
Create Date: 2026-09-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c4e1f90b32"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "buffer_connections",
        sa.Column(
            "provider",
            sa.String(length=30),
            nullable=False,
            server_default="buffer",
        ),
    )
    op.add_column(
        "buffer_connections",
        sa.Column("provider_account_ref", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_buffer_connection_user_provider",
        "buffer_connections",
        ["user_id", "provider"],
    )

    op.add_column(
        "social_channels",
        sa.Column(
            "provider",
            sa.String(length=30),
            nullable=False,
            server_default="buffer",
        ),
    )
    # Campaign targeting filters channels by provider, so the column is read on
    # every campaign launch alongside is_active/publication_mode.
    op.create_index(
        "idx_social_channels_provider",
        "social_channels",
        ["provider"],
    )


def downgrade() -> None:
    op.drop_index("idx_social_channels_provider", table_name="social_channels")
    op.drop_column("social_channels", "provider")
    op.drop_constraint(
        "uq_buffer_connection_user_provider",
        "buffer_connections",
        type_="unique",
    )
    op.drop_column("buffer_connections", "provider_account_ref")
    op.drop_column("buffer_connections", "provider")
