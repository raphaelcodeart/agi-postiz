"""omni knowledge base: aziende come cartelle dei documenti

Revision ID: c5a83f0e9d21
Revises: b7e2d91c4a18
Create Date: 2026-10-15

L'etichetta di testo libero omni_knowledge_documents.company diventa una
tabella vera (omni_knowledge_companies) con contatti e descrizione. Le
etichette gia' usate diventano aziende con lo stesso nome, e i documenti
restano attaccati alla loro: niente da rifare a mano dopo l'aggiornamento.
Le intestazioni dei blocchi ("Azienda: X | ...") non cambiano, quindi gli
embedding gia' calcolati restano validi.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5a83f0e9d21"
down_revision: Union[str, None] = "b7e2d91c4a18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "omni_knowledge_companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(100), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("owner_id", "name", name="uq_omni_knowledge_company_owner_name"),
    )
    op.create_index("ix_omni_knowledge_companies_owner_id", "omni_knowledge_companies", ["owner_id"])

    op.add_column(
        "omni_knowledge_documents",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("omni_knowledge_companies.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_omni_knowledge_documents_company_id", "omni_knowledge_documents", ["company_id"])

    # Un'azienda per ogni etichetta distinta (stesso proprietario, stesso nome
    # a meno di spazi), poi i documenti puntano alla loro.
    op.execute("""
        INSERT INTO omni_knowledge_companies (id, owner_id, name, created_at, updated_at)
        SELECT gen_random_uuid(), owner_id, btrim(company), min(created_at), now()
        FROM omni_knowledge_documents
        WHERE company IS NOT NULL AND btrim(company) <> ''
        GROUP BY owner_id, btrim(company)
    """)
    op.execute("""
        UPDATE omni_knowledge_documents d SET company_id = c.id
        FROM omni_knowledge_companies c
        WHERE c.owner_id = d.owner_id AND c.name = btrim(d.company)
    """)
    op.drop_column("omni_knowledge_documents", "company")


def downgrade() -> None:
    op.add_column("omni_knowledge_documents", sa.Column("company", sa.String(255), nullable=True))
    op.execute("""
        UPDATE omni_knowledge_documents d SET company = c.name
        FROM omni_knowledge_companies c WHERE c.id = d.company_id
    """)
    # Le schede azienda esistono solo con la tabella aziende.
    op.execute("DELETE FROM omni_knowledge_documents WHERE kind = 'profile'")
    op.drop_index("ix_omni_knowledge_documents_company_id", table_name="omni_knowledge_documents")
    op.drop_column("omni_knowledge_documents", "company_id")
    op.drop_index("ix_omni_knowledge_companies_owner_id", table_name="omni_knowledge_companies")
    op.drop_table("omni_knowledge_companies")
