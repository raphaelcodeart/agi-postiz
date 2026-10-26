"""conferma email, consenso privacy e reset password del portale

Aggiunge quello che serviva per due cose che mancavano al portale promoter:

1. La registrazione manda un'email di benvenuto con un link che conferma
   l'indirizzo e vale come accettazione di informativa e termini. Finche' non e'
   cliccato il portale non si apre.
2. Chi perde la password puo' chiederne il reset per email invece di scrivere a
   un amministratore.

Gli account gia' esistenti NON vengono considerati confermati. Quando si sono
iscritti l'informativa privacy e i termini non c'erano ancora, quindi un loro
consenso non esiste: retrodatarlo alla data di creazione vorrebbe dire scrivere
nel database un'accettazione mai data. Al prossimo accesso trovano quindi la
finestra bloccante, da cui si fanno mandare l'email con il link che conferma
l'indirizzo e vale come accettazione - lo stesso passaggio dei nuovi iscritti.

Per loro si accende ``verification_retroactive``: serve solo a scegliere il
testo giusto (nella finestra e nell'email) per chi e' iscritto da tempo e non
va accolto con un "benvenuto, il tuo account e' stato creato". Gli utenti creati
da un amministratore e mai registrati non hanno password e restano fuori dal
conto: quando rivendicheranno l'account seguiranno la strada dei nuovi iscritti.

Revision ID: a4f19c3b7d52
Revises: e3c9a4d7b812
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a4f19c3b7d52"
down_revision: Union[str, None] = "e3c9a4d7b812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users", sa.Column("privacy_accepted_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.add_column(
        "users",
        sa.Column(
            "verification_retroactive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Chi ha gia' credenziali del portale si e' iscritto prima che esistessero
    # informativa e termini: la conferma la dovra' dare, ma con il testo per chi
    # c'era gia'. Vedi il perche' in testa al file.
    op.execute("UPDATE users SET verification_retroactive = true WHERE password_hash IS NOT NULL")

    op.create_table(
        "user_auth_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # CASCADE: i token di un utente cancellato non hanno nessun significato
        # residuo, e lasciarli in giro vorrebbe dire tenere in vita dei link.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_user_auth_tokens_token_hash"),
    )
    op.create_index("ix_user_auth_tokens_user_id", "user_auth_tokens", ["user_id"])
    op.create_index("ix_user_auth_tokens_token_hash", "user_auth_tokens", ["token_hash"])
    op.create_index("ix_user_auth_tokens_user_purpose", "user_auth_tokens", ["user_id", "purpose"])
    op.create_index(
        "ix_user_auth_tokens_purpose_created", "user_auth_tokens", ["purpose", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_auth_tokens_purpose_created", table_name="user_auth_tokens")
    op.drop_index("ix_user_auth_tokens_user_purpose", table_name="user_auth_tokens")
    op.drop_index("ix_user_auth_tokens_token_hash", table_name="user_auth_tokens")
    op.drop_index("ix_user_auth_tokens_user_id", table_name="user_auth_tokens")
    op.drop_table("user_auth_tokens")
    op.drop_column("users", "verification_retroactive")
    op.drop_column("users", "privacy_accepted_at")
    op.drop_column("users", "email_verified_at")
