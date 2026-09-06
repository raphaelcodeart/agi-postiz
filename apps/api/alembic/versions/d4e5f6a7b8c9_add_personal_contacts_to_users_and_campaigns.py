"""add personal contacts to users and campaigns

Revision ID: d4e5f6a7b8c9
Revises: 9c1f3a7e2b6d
Create Date: 2026-08-26 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = '9c1f3a7e2b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default required here (unlike the plain add_column below): campaigns
    # already has rows in production, and a NOT NULL column needs a value for
    # them - same two-step pattern as 6ad75c20ec09_add_referral_link_to_users_and_campaigns.py.
    op.add_column('campaigns', sa.Column('include_personal_contacts', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column('campaigns', 'include_personal_contacts', server_default=None)
    op.add_column('users', sa.Column('personal_contacts', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'personal_contacts')
    op.drop_column('campaigns', 'include_personal_contacts')
