"""add missing metric columns to stat_metric_history

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-26 21:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # stat_metric_history was missing 3 of the 9 numeric metric columns present
    # on stat_post_metrics (likes, impressions, reach) - _apply_metrics
    # (app/tasks/statistics.py) writes both tables from the same
    # ALL_METRIC_COLUMNS-keyed kwargs dict, so the mismatch raised an unhandled
    # TypeError on every single post sync/refresh. All nullable, same as their
    # stat_post_metrics counterparts.
    op.add_column('stat_metric_history', sa.Column('likes', sa.Float(), nullable=True))
    op.add_column('stat_metric_history', sa.Column('impressions', sa.Float(), nullable=True))
    op.add_column('stat_metric_history', sa.Column('reach', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('stat_metric_history', 'reach')
    op.drop_column('stat_metric_history', 'impressions')
    op.drop_column('stat_metric_history', 'likes')
