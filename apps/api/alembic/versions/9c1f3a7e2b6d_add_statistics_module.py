"""add statistics module

Revision ID: 9c1f3a7e2b6d
Revises: 6ad75c20ec09
Create Date: 2026-08-26 00:00:00.000000

Adds the "Statistiche" module (persisted, browsable Buffer post metrics per
promoter/canale/campagna) as a self-contained set of new tables, prefixed
stat_. Nothing existing is altered - every new table's only link back to the
rest of the platform is a set of read-only foreign keys towards
publications/campaigns/users/social_channels/buffer_connections/
administrators. See docs/STATISTICS.md.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9c1f3a7e2b6d'
down_revision: Union[str, None] = '6ad75c20ec09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'stat_sync_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('scope', sa.String(length=20), nullable=False),
        sa.Column('scope_user_id', sa.UUID(), nullable=True),
        sa.Column('scope_campaign_id', sa.UUID(), nullable=True),
        sa.Column('triggered_by', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('total_posts', sa.Integer(), nullable=False),
        sa.Column('synced_posts', sa.Integer(), nullable=False),
        sa.Column('failed_posts', sa.Integer(), nullable=False),
        sa.Column('skipped_posts', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.String(length=1000), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['scope_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['scope_campaign_id'], ['campaigns.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['triggered_by'], ['administrators.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_stat_sync_runs_scope_user', 'stat_sync_runs', ['scope_user_id'])
    op.create_index('idx_stat_sync_runs_scope_campaign', 'stat_sync_runs', ['scope_campaign_id'])
    op.create_index('idx_stat_sync_runs_started_at', 'stat_sync_runs', ['started_at'])

    op.create_table(
        'stat_post_metrics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('publication_id', sa.UUID(), nullable=False),
        sa.Column('campaign_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('social_channel_id', sa.UUID(), nullable=False),
        sa.Column('buffer_connection_id', sa.UUID(), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('external_post_id', sa.String(length=255), nullable=False),
        sa.Column('external_post_url', sa.String(length=1000), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reactions', sa.Float(), nullable=True),
        sa.Column('likes', sa.Float(), nullable=True),
        sa.Column('views', sa.Float(), nullable=True),
        sa.Column('impressions', sa.Float(), nullable=True),
        sa.Column('reach', sa.Float(), nullable=True),
        sa.Column('follows', sa.Float(), nullable=True),
        sa.Column('clicks', sa.Float(), nullable=True),
        sa.Column('comments', sa.Float(), nullable=True),
        sa.Column('shares', sa.Float(), nullable=True),
        sa.Column('engagement_rate', sa.Float(), nullable=True),
        sa.Column('metrics_raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('metrics_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_error', sa.String(length=1000), nullable=True),
        sa.Column('last_sync_run_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['publication_id'], ['publications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['social_channel_id'], ['social_channels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['buffer_connection_id'], ['buffer_connections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['last_sync_run_id'], ['stat_sync_runs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('publication_id', name='uq_stat_post_metrics_publication'),
    )
    op.create_index('idx_stat_post_metrics_user_id', 'stat_post_metrics', ['user_id'])
    op.create_index('idx_stat_post_metrics_campaign_id', 'stat_post_metrics', ['campaign_id'])
    op.create_index('idx_stat_post_metrics_social_channel_id', 'stat_post_metrics', ['social_channel_id'])
    op.create_index('idx_stat_post_metrics_last_synced_at', 'stat_post_metrics', ['last_synced_at'])

    op.create_table(
        'stat_metric_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('publication_id', sa.UUID(), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reactions', sa.Float(), nullable=True),
        sa.Column('views', sa.Float(), nullable=True),
        sa.Column('follows', sa.Float(), nullable=True),
        sa.Column('clicks', sa.Float(), nullable=True),
        sa.Column('comments', sa.Float(), nullable=True),
        sa.Column('shares', sa.Float(), nullable=True),
        sa.Column('engagement_rate', sa.Float(), nullable=True),
        sa.Column('metrics_raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['publication_id'], ['publications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_stat_metric_history_publication_synced',
        'stat_metric_history',
        ['publication_id', 'synced_at'],
    )


def downgrade() -> None:
    op.drop_index('idx_stat_metric_history_publication_synced', table_name='stat_metric_history')
    op.drop_table('stat_metric_history')

    op.drop_index('idx_stat_post_metrics_last_synced_at', table_name='stat_post_metrics')
    op.drop_index('idx_stat_post_metrics_social_channel_id', table_name='stat_post_metrics')
    op.drop_index('idx_stat_post_metrics_campaign_id', table_name='stat_post_metrics')
    op.drop_index('idx_stat_post_metrics_user_id', table_name='stat_post_metrics')
    op.drop_table('stat_post_metrics')

    op.drop_index('idx_stat_sync_runs_started_at', table_name='stat_sync_runs')
    op.drop_index('idx_stat_sync_runs_scope_campaign', table_name='stat_sync_runs')
    op.drop_index('idx_stat_sync_runs_scope_user', table_name='stat_sync_runs')
    op.drop_table('stat_sync_runs')
