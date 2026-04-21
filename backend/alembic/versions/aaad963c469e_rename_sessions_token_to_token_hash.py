"""rename sessions.token to token_hash

Revision ID: aaad963c469e
Revises: e741951e9b5f
Create Date: 2026-04-21 02:32:47.519273

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aaad963c469e"
down_revision: str | None = "e741951e9b5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add nullable first — existing rows have a token value but no hash.
    # Existing sessions are invalidated (old tokens are unverifiable after the
    # rename; users will need to log in again after this migration).
    op.execute("DELETE FROM sessions")
    op.add_column("sessions", sa.Column("token_hash", sa.String(length=64), nullable=False))
    op.drop_index("ix_sessions_token", table_name="sessions")
    op.create_index(op.f("ix_sessions_token_hash"), "sessions", ["token_hash"], unique=True)
    op.drop_column("sessions", "token")


def downgrade() -> None:
    """Downgrade schema."""
    # Hashes are unrecoverable; clear sessions before restoring NOT NULL token column.
    op.execute("DELETE FROM sessions")
    op.add_column(
        "sessions", sa.Column("token", sa.VARCHAR(length=128), autoincrement=False, nullable=False)
    )
    op.drop_index(op.f("ix_sessions_token_hash"), table_name="sessions")
    op.create_index("ix_sessions_token", "sessions", ["token"], unique=True)
    op.drop_column("sessions", "token_hash")
