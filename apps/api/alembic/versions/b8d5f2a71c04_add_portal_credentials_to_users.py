"""add portal credentials to users

Gives end users the ability to sign in on our own dashboard. All three columns
are nullable: every user that exists today was created by an administrator and
has no portal credentials, which is exactly what NULL means here - they cannot
sign in until a password is set, and nothing about their campaign behaviour
changes.

Revision ID: b8d5f2a71c04
Revises: a7c4e1f90b32
Create Date: 2026-09-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8d5f2a71c04"
down_revision: Union[str, None] = "a7c4e1f90b32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Argon2 hash. Never a plaintext password, and never returned by any
    # endpoint - the portal schemas omit it entirely.
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    # Marks an account created through public registration rather than by an
    # administrator. Those start status="inactive" so they are not targetable by
    # campaigns until vetted - see app/api/v1/portal.py::register.
    op.add_column("users", sa.Column("self_registered_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "self_registered_at")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "password_hash")
