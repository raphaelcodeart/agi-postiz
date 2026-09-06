"""add omni_customers.is_blocked

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-10 15:00:00.000000

Additive column for the "block customer" action - a blocked customer's new
messages are still recorded but never generate an AI draft (see
app/models/omnichannel.py::OmniCustomer.is_blocked docstring).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('omni_customers', sa.Column('is_blocked', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column('omni_customers', 'is_blocked', server_default=None)


def downgrade() -> None:
    op.drop_column('omni_customers', 'is_blocked')
