"""profilo obbligatorio al primo accesso: citta', CAP, gruppi

Revision ID: f2c7a9e3d4b1
Revises: e6b1d4f8a2c7
Create Date: 2026-10-25

Tre colonne su users. profile_completed_at resta NULL anche per chi era gia'
iscritto: il portale chiede a tutti, una volta, citta', CAP e gruppi di
partecipazione (docs/FUNCTIONALITY.md §4-ter). Niente da retrodatare: non
abbiamo quei dati per nessuno.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f2c7a9e3d4b1"
down_revision: Union[str, None] = "e6b1d4f8a2c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("city", sa.String(120), nullable=True))
    op.add_column("users", sa.Column("postal_code", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("profile_completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "profile_completed_at")
    op.drop_column("users", "postal_code")
    op.drop_column("users", "city")
