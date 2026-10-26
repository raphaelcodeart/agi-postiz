"""avvisi di servizio agli utenti (user_notifications)

Revision ID: e6b1d4f8a2c7
Revises: c5a83f0e9d21
Create Date: 2026-10-25

Registro degli avvisi di servizio che l'amministrazione manda ai promoter,
a partire da quello sui canali social insufficienti (vedi
docs/FUNCTIONALITY.md §3). Una riga per invio: la pagina mostra quando e
quante volte ogni utente e' stato avvisato, e "Notifica a tutti" salta chi
ha gia' ricevuto il messaggio di recente.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e6b1d4f8a2c7"
down_revision: Union[str, None] = "c5a83f0e9d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column(
            "sent_by_administrator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("administrators.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_user_notifications_user_kind_sent", "user_notifications", ["user_id", "kind", "sent_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_user_notifications_user_kind_sent", table_name="user_notifications")
    op.drop_table("user_notifications")
