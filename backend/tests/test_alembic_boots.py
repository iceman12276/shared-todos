"""Verify Alembic migrate-up and migrate-down round-trips against real Postgres.

This test was recommended in the PR-1 validation report as a natural addition
alongside the first real migration.
"""
import pytest
from alembic.config import Config

from alembic import command


@pytest.fixture
def alembic_cfg() -> Config:
    cfg = Config("/home/isaac/Desktop/dev/shared-todos-pr1/backend/alembic.ini")
    script_loc = "/home/isaac/Desktop/dev/shared-todos-pr1/backend/alembic"
    cfg.set_main_option("script_location", script_loc)
    return cfg


def test_alembic_upgrade_then_downgrade(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
