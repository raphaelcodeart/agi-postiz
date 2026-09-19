"""portal self-service statistics sync

Revision ID: c7a2e9f14b30
Revises: a3f81c25d7e0
Create Date: 2026-09-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a2e9f14b30'
down_revision: Union[str, None] = 'a3f81c25d7e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Un sync di statistiche puo' ora essere lanciato anche dal promoter dal suo
    # portale (scope="user", sempre sui propri post - app/api/v1/portal_statistics.py),
    # non solo da un amministratore. stat_sync_runs.triggered_by punta ad
    # administrators.id, quindi non puo' registrare chi e': senza questa colonna
    # un run self-service resterebbe indistinguibile da uno di un amministratore
    # poi cancellato (quella FK e' gia' ondelete SET NULL).
    op.add_column(
        'stat_sync_runs',
        sa.Column('triggered_by_user_id', sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_stat_sync_runs_triggered_by_user',
        'stat_sync_runs',
        'users',
        ['triggered_by_user_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_stat_sync_runs_triggered_by_user', 'stat_sync_runs', type_='foreignkey')
    op.drop_column('stat_sync_runs', 'triggered_by_user_id')
