"""Verify Alembic migrate-up and migrate-down round-trips against real Postgres.

This test was recommended in the PR-1 validation report as a natural addition
alongside the first real migration.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _make_cfg() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


def test_alembic_upgrade_then_downgrade() -> None:
    alembic_cfg = _make_cfg()
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
