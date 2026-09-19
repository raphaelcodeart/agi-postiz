"""campaign proposals: custom video request and desired platforms

Revision ID: e3c9a4d7b812
Revises: d8b3f6a1c927
Create Date: 2026-09-19 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e3c9a4d7b812'
down_revision: Union[str, None] = 'd8b3f6a1c927'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Il promoter puo' chiedere ad AGI Post di realizzargli un video su misura
    # e indicare su quali social vorrebbe la campagna. Solo colonne nuove, e
    # solo su campaign_proposals: `campaigns` resta intatta.
    op.add_column('campaign_proposals', sa.Column('video_request', sa.String(length=2000), nullable=True))
    op.add_column(
        'campaign_proposals',
        sa.Column(
            'target_platforms',
            postgresql.ARRAY(sa.String(length=30)),
            nullable=False,
            server_default='{}',
        ),
    )


def downgrade() -> None:
    op.drop_column('campaign_proposals', 'target_platforms')
    op.drop_column('campaign_proposals', 'video_request')
