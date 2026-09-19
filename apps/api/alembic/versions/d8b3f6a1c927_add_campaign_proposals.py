"""add campaign proposals from portal users

Revision ID: d8b3f6a1c927
Revises: c7a2e9f14b30
Create Date: 2026-09-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8b3f6a1c927'
down_revision: Union[str, None] = 'c7a2e9f14b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tabella nuova, separata da `campaigns` di proposito: vedi il docstring di
    # app/models/campaign_proposal.py per il perche' una proposta non e' uno
    # stato in piu' su una campagna. Nessuna modifica a `campaigns`.
    op.create_table(
        'campaign_proposals',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('default_text', sa.String(length=5000), nullable=False),
        sa.Column('notes', sa.String(length=2000), nullable=True),
        sa.Column('media_file_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('suggested_scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='draft'),
        sa.Column('review_notes', sa.String(length=2000), nullable=True),
        sa.Column('reviewed_by', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('campaign_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['media_file_id'], ['media_files.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['administrators.id'], ondelete='SET NULL'),
        # SET NULL e non CASCADE: se la campagna nata da una proposta viene
        # cancellata, la proposta resta - e' il documento che dice che quel
        # promoter aveva contribuito, e va conservato anche se la campagna no.
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='SET NULL'),
    )
    op.create_index('idx_campaign_proposals_status', 'campaign_proposals', ['status'])
    op.create_index('idx_campaign_proposals_user_status', 'campaign_proposals', ['user_id', 'status'])
    op.create_index(op.f('ix_campaign_proposals_user_id'), 'campaign_proposals', ['user_id'])

    # La libreria media e' condivisa fra amministratore e promoter da quando
    # questi ultimi possono allegare un video a una proposta. NULL = caricato da
    # un amministratore, com'e' stato finora per ogni riga esistente.
    op.add_column('media_files', sa.Column('uploaded_by_user_id', sa.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_media_files_uploaded_by_user', 'media_files', 'users',
        ['uploaded_by_user_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_media_files_uploaded_by_user', 'media_files', type_='foreignkey')
    op.drop_column('media_files', 'uploaded_by_user_id')
    op.drop_index(op.f('ix_campaign_proposals_user_id'), table_name='campaign_proposals')
    op.drop_index('idx_campaign_proposals_user_status', table_name='campaign_proposals')
    op.drop_index('idx_campaign_proposals_status', table_name='campaign_proposals')
    op.drop_table('campaign_proposals')
