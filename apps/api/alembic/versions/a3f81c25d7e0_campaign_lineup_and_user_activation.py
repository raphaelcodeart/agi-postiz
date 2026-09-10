"""campaign line-up (opt-out participation) and automatic user activation

Two changes that arrived together because they depend on each other.

The line-up lets an administrator announce a campaign to the people it targets
before anything is sent, and lets those people take their channels out of it
while the window is open. That is what makes the second change safe: portal
registrations can activate themselves, because being active no longer means
being published to without a say.

The data step at the end activates the accounts that were already waiting. Those
are exactly the manual activations this removes the need for, and leaving them
inactive would have meant doing the last round of them by hand anyway.

Revision ID: a3f81c25d7e0
Revises: e2f47b9c1d63
Create Date: 2026-09-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3f81c25d7e0"
down_revision: Union[str, None] = "e2f47b9c1d63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- campaigns: the announced line-up -----------------------------------
    # server_default on all three: existing rows must keep behaving exactly as
    # they do today ("automatic", no window, no auto-launch), and the columns are
    # NOT NULL, so a default is also what lets them be added without rewriting
    # every row by hand.
    op.add_column(
        "campaigns",
        sa.Column("participation_mode", sa.String(length=30), server_default="automatic", nullable=False),
    )
    op.add_column("campaigns", sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("campaigns", sa.Column("opt_out_deadline_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "campaigns",
        sa.Column("auto_launch_at_deadline", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    # --- campaign_participants ----------------------------------------------
    op.create_table(
        "campaign_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("social_channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="included", nullable=False),
        sa.Column("added_by", sa.String(length=20), server_default="admin", nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["social_channel_id"], ["social_channels.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "campaign_id", "social_channel_id", name="uq_campaign_participant_campaign_channel"
        ),
    )
    op.create_index("idx_campaign_participants_user", "campaign_participants", ["user_id"])
    op.create_index(
        "idx_campaign_participants_campaign_status", "campaign_participants", ["campaign_id", "status"]
    )

    # --- platform_settings: automatic activation ----------------------------
    op.add_column(
        "platform_settings",
        sa.Column("auto_activate_new_users", sa.Boolean(), server_default=sa.true(), nullable=False),
    )

    # --- data: clear the backlog of pending activations ---------------------
    # Only accounts that registered themselves and are sitting at "inactive".
    # Deliberately NOT touching "suspended": that status is a decision somebody
    # made about a specific account, and a migration must not quietly undo it.
    op.execute(
        """
        UPDATE users
           SET status = 'active',
               updated_at = NOW()
         WHERE status = 'inactive'
           AND self_registered_at IS NOT NULL
           AND deleted_at IS NULL
        """
    )


def downgrade() -> None:
    # The activation above is not reversed: flipping accounts back to "inactive"
    # would take out any that an administrator activated on purpose, before or
    # after this ran, and there is no record here of which were which.
    op.drop_column("platform_settings", "auto_activate_new_users")
    op.drop_index("idx_campaign_participants_campaign_status", table_name="campaign_participants")
    op.drop_index("idx_campaign_participants_user", table_name="campaign_participants")
    op.drop_table("campaign_participants")
    op.drop_column("campaigns", "auto_launch_at_deadline")
    op.drop_column("campaigns", "opt_out_deadline_at")
    op.drop_column("campaigns", "announced_at")
    op.drop_column("campaigns", "participation_mode")
