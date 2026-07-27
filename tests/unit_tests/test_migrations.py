from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata, render_python_code
from alembic.config import Config as AlembicConfig
from alembic.migration import MigrationContext
from alembic.operations import ops

from polyglot_pigeon.db.base import Base
from polyglot_pigeon.db.types import UtcDateTime

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def alembic_config(db_settings) -> AlembicConfig:
    cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", db_settings.url)
    return cfg


@pytest.fixture(autouse=True)
def _reset_schema(db_engine, alembic_config):
    """Every test starts and ends at 'base' so runs don't interfere."""
    command.downgrade(alembic_config, "base")
    yield
    command.downgrade(alembic_config, "base")


def test_upgrade_downgrade_cycle(alembic_config, db_engine):
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


def test_autogenerate_empty_diff_on_clean_head(alembic_config, db_engine):
    command.upgrade(alembic_config, "head")

    with db_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        diff = compare_metadata(ctx, Base.metadata)

    assert diff == []


def test_autogenerate_renders_utcdatetime_via_module_prefix(db_engine):
    """The type must render as `pp.UtcDateTime(...)`, not its DATETIME impl.

    Without `user_module_prefix` wired up in migrations/env.py, Alembic
    autogenerate falls back to rendering the impl type and every later
    migration quietly loses the UTC/naive-rejection behaviour.
    """
    add_column_op = ops.AddColumnOp(
        "probe", sa.Column("created_at", UtcDateTime(), nullable=False)
    )

    with db_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        rendered = render_python_code(
            ops.UpgradeOps(ops=[add_column_op]),
            user_module_prefix="pp.",
            migration_context=ctx,
        )

    assert "pp.UtcDateTime(" in rendered
    assert "DATETIME" not in rendered
