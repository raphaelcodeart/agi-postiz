"""omni knowledge base: istruzioni, aziende, file, embedding e ricerca full-text

Revision ID: b7e2d91c4a18
Revises: a4f19c3b7d52
Create Date: 2026-10-15

Solo aggiunte: nessuna colonna esistente cambia significato. Gli indici GIN
coprono esattamente le espressioni usate da knowledge._fts_search() - se una
delle due cambia, va cambiata anche l'altra, altrimenti Postgres torna alla
scansione sequenziale senza dirlo.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2d91c4a18"
down_revision: Union[str, None] = "a4f19c3b7d52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FTS_DOCUMENT = "coalesce(heading, '') || ' ' || content"


def upgrade() -> None:
    op.add_column("omni_knowledge_documents", sa.Column("kind", sa.String(20), nullable=False, server_default="document"))
    op.add_column("omni_knowledge_documents", sa.Column("always_on", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("omni_knowledge_documents", sa.Column("company", sa.String(255), nullable=True))
    op.add_column("omni_knowledge_documents", sa.Column("file_name", sa.String(255), nullable=True))
    op.add_column("omni_knowledge_documents", sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("omni_knowledge_documents", sa.Column("error_message", sa.Text(), nullable=True))

    op.add_column("omni_knowledge_chunks", sa.Column("heading", sa.String(600), nullable=True))
    op.add_column("omni_knowledge_chunks", sa.Column("embedding", sa.LargeBinary(), nullable=True))
    op.add_column("omni_knowledge_chunks", sa.Column("embedding_model", sa.String(100), nullable=True))
    op.add_column("omni_knowledge_chunks", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True))

    # I documenti gia' presenti: intestazione e conteggio come li scriverebbe
    # oggi knowledge.rebuild_chunks(). Gli embedding li calcola il task
    # periodico al primo giro.
    op.execute("""
        UPDATE omni_knowledge_chunks c SET heading = 'Documento: ' || d.title
        FROM omni_knowledge_documents d WHERE d.id = c.document_id AND c.heading IS NULL
    """)
    op.execute("""
        UPDATE omni_knowledge_documents d
        SET chunk_count = (SELECT count(*) FROM omni_knowledge_chunks c WHERE c.document_id = d.id)
    """)

    op.create_index("ix_omni_knowledge_chunks_document_id", "omni_knowledge_chunks", ["document_id"])
    op.execute(f"CREATE INDEX ix_omni_knowledge_chunks_fts_it ON omni_knowledge_chunks USING gin (to_tsvector('italian', {_FTS_DOCUMENT}))")
    op.execute(f"CREATE INDEX ix_omni_knowledge_chunks_fts_simple ON omni_knowledge_chunks USING gin (to_tsvector('simple', {_FTS_DOCUMENT}))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_omni_knowledge_chunks_fts_simple")
    op.execute("DROP INDEX IF EXISTS ix_omni_knowledge_chunks_fts_it")
    op.drop_index("ix_omni_knowledge_chunks_document_id", table_name="omni_knowledge_chunks")
    for column in ("embedded_at", "embedding_model", "embedding", "heading"):
        op.drop_column("omni_knowledge_chunks", column)
    for column in ("error_message", "chunk_count", "file_name", "company", "always_on", "kind"):
        op.drop_column("omni_knowledge_documents", column)
