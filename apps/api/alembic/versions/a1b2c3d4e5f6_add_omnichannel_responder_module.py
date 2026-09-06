"""add omnichannel responder module

Revision ID: a1b2c3d4e5f6
Revises: f977e27daa7d
Create Date: 2026-08-10 00:00:00.000000

Adds the full "Omnichannel Responder" module (unified AI inbox with human
approval) as a self-contained set of new tables, prefixed omni_. Nothing
existing is altered - every new table's only link back to the rest of the
platform is owner_id -> administrators.id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f977e27daa7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('omni_channel_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('channel', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('external_account_id', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('access_token_encrypted', sa.Text(), nullable=True),
        sa.Column('webhook_secret', sa.String(length=64), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_omni_channel_accounts_owner_id', 'omni_channel_accounts', ['owner_id'])

    op.create_table('omni_customers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('first_name', sa.String(length=255), nullable=True),
        sa.Column('last_name', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('timezone', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_contact_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_omni_customers_owner_id', 'omni_customers', ['owner_id'])

    op.create_table('omni_customer_identities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('channel', sa.String(length=50), nullable=False),
        sa.Column('external_user_id', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['omni_customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_id', 'channel', 'external_user_id', name='uq_omni_identity_owner_channel_external'),
    )
    op.create_index('ix_omni_customer_identities_owner_id', 'omni_customer_identities', ['owner_id'])

    op.create_table('omni_conversations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('channel_account_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('assigned_admin_id', sa.UUID(), nullable=True),
        sa.Column('unread_count', sa.Integer(), nullable=False),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['channel_account_id'], ['omni_channel_accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['omni_customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_admin_id'], ['administrators.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_omni_conversations_owner_id', 'omni_conversations', ['owner_id'])

    op.create_table('omni_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('channel_account_id', sa.UUID(), nullable=False),
        sa.Column('direction', sa.String(length=20), nullable=False),
        sa.Column('sender_type', sa.String(length=20), nullable=False),
        sa.Column('external_message_id', sa.String(length=255), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('message_type', sa.String(length=20), nullable=False),
        sa.Column('attachments', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['omni_conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['channel_account_id'], ['omni_channel_accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('channel_account_id', 'external_message_id', name='uq_omni_message_channel_external'),
    )
    op.create_index('ix_omni_messages_owner_id', 'omni_messages', ['owner_id'])

    op.create_table('omni_ai_drafts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('source_message_id', sa.UUID(), nullable=True),
        sa.Column('original_ai_text', sa.Text(), nullable=True),
        sa.Column('edited_text', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('prompt_version', sa.String(length=50), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('sensitive_category', sa.String(length=100), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by', sa.UUID(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['omni_conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_message_id'], ['omni_messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by'], ['administrators.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_omni_ai_drafts_owner_id', 'omni_ai_drafts', ['owner_id'])

    op.create_table('omni_ai_agent_configs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('system_prompt', sa.Text(), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=False),
        sa.Column('tone', sa.String(length=50), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=False),
        sa.Column('company_description', sa.Text(), nullable=True),
        sa.Column('allowed_topics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('forbidden_topics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('signature', sa.String(length=255), nullable=True),
        sa.Column('max_context_messages', sa.Integer(), nullable=False),
        sa.Column('knowledge_base_enabled', sa.Boolean(), nullable=False),
        sa.Column('automatic_language_detection', sa.Boolean(), nullable=False),
        sa.Column('response_mode', sa.String(length=30), nullable=False),
        sa.Column('sensitive_categories', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_id', name='uq_omni_ai_agent_config_owner'),
    )

    op.create_table('omni_knowledge_documents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=20), nullable=False),
        sa.Column('content_text', sa.Text(), nullable=True),
        sa.Column('source_url', sa.String(length=1000), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_omni_knowledge_documents_owner_id', 'omni_knowledge_documents', ['owner_id'])

    op.create_table('omni_knowledge_chunks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['omni_knowledge_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_omni_knowledge_chunks_owner_id', 'omni_knowledge_chunks', ['owner_id'])

    op.create_table('omni_tags',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_id', 'name', name='uq_omni_tag_owner_name'),
    )

    op.create_table('omni_conversation_tags',
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('tag_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['omni_conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['omni_tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('conversation_id', 'tag_id'),
    )

    op.create_table('omni_internal_notes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('admin_id', sa.UUID(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('mentions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['omni_conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['admin_id'], ['administrators.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_omni_internal_notes_owner_id', 'omni_internal_notes', ['owner_id'])

    op.create_table('omni_audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('admin_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['admin_id'], ['administrators.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_omni_audit_logs_owner_id', 'omni_audit_logs', ['owner_id'])

    op.create_table('omni_notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('admin_id', sa.UUID(), nullable=True),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('entity_type', sa.String(length=50), nullable=True),
        sa.Column('entity_id', sa.UUID(), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['admin_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_omni_notifications_owner_id', 'omni_notifications', ['owner_id'])

    op.create_table('omni_ai_usage',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=True),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('estimated_cost', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['administrators.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['omni_conversations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_omni_ai_usage_owner_id', 'omni_ai_usage', ['owner_id'])


def downgrade() -> None:
    op.drop_table('omni_ai_usage')
    op.drop_table('omni_notifications')
    op.drop_table('omni_audit_logs')
    op.drop_table('omni_internal_notes')
    op.drop_table('omni_conversation_tags')
    op.drop_table('omni_tags')
    op.drop_table('omni_knowledge_chunks')
    op.drop_table('omni_knowledge_documents')
    op.drop_table('omni_ai_agent_configs')
    op.drop_table('omni_ai_drafts')
    op.drop_table('omni_messages')
    op.drop_table('omni_conversations')
    op.drop_table('omni_customer_identities')
    op.drop_table('omni_customers')
    op.drop_table('omni_channel_accounts')
