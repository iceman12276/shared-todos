"""add user check constraint has_auth_method

Revision ID: 380d8a29fa13
Revises: aaad963c469e
Create Date: 2026-04-21 02:37:56.508328

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "380d8a29fa13"
down_revision: str | None = "aaad963c469e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "ck_users_has_auth_method",
        "users",
        "password_hash IS NOT NULL OR google_sub IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_users_has_auth_method", "users", type_="check")
