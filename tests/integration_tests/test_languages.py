"""Tests for the `languages` table that need the real, migrated schema and
seed data (PP-05) — moved out of the unit suite by PP-28, since Alembic opens
its own engine independent of any test fixture and can't run against
in-memory SQLite."""

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from polyglot_pigeon.shared.db.models import Language

EXPECTED_CODES = {"en", "de", "ru", "it", "es", "tr", "pl"}


class TestLanguagesTable:
    """Tests that need the real, migrated `languages` table and its seed."""

    @pytest.fixture(autouse=True)
    def _migrated_to_head(self, db_engine, alembic_config):
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")
        yield
        command.downgrade(alembic_config, "base")

    def test_code_is_a_natural_string_primary_key(self, db_engine):
        inspector = inspect(db_engine)
        columns = {c["name"]: c for c in inspector.get_columns("languages")}
        pk = inspector.get_pk_constraint("languages")

        assert pk["constrained_columns"] == ["code"]
        assert isinstance(columns["code"]["type"], sa.String)
        assert columns["code"]["type"].length == 8
        assert columns["code"]["autoincrement"] is not True

    def test_seed_migration_inserts_the_initially_supported_languages(self, db_engine):
        with db_engine.connect() as conn:
            rows = conn.execute(
                select(Language.code, Language.name_en, Language.name_native)
            ).all()

        codes = {row.code for row in rows}
        assert codes == EXPECTED_CODES
        for row in rows:
            assert row.name_en
            assert row.name_native

    def test_seed_migration_is_idempotent_across_downgrade_upgrade(
        self, db_engine, alembic_config
    ):
        with db_engine.connect() as conn:
            first_count = conn.execute(
                select(sa.func.count()).select_from(Language)
            ).scalar_one()

        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")

        with db_engine.connect() as conn:
            second_count = conn.execute(
                select(sa.func.count()).select_from(Language)
            ).scalar_one()

        assert first_count == len(EXPECTED_CODES)
        assert second_count == first_count

    def test_unknown_language_code_is_rejected_by_a_foreign_key(self, db_engine):
        # A fresh MetaData, with `languages` reflected into it rather than
        # imported from `Base.metadata` — sharing `Base.metadata` would
        # register this throwaway probe table permanently and break
        # `test_autogenerate_empty_diff_on_clean_head` in test_migrations.py.
        # The FK string `"languages.code"` only resolves against a table in
        # the *same* MetaData collection, hence the reflection.
        probe_metadata = sa.MetaData()
        sa.Table("languages", probe_metadata, autoload_with=db_engine)
        probe = sa.Table(
            "language_fk_probe",
            probe_metadata,
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column(
                "language_code",
                sa.String(8),
                sa.ForeignKey("languages.code"),
                nullable=False,
            ),
            mysql_charset="utf8mb4",
            mysql_collate="utf8mb4_unicode_ci",
        )
        # `tables=[probe]` on both calls: without it, `drop_all` would also
        # try to drop the real, reflected `languages` table.
        probe_metadata.create_all(db_engine, tables=[probe])
        try:
            with pytest.raises(IntegrityError):
                with db_engine.begin() as conn:
                    conn.execute(probe.insert(), {"language_code": "xx"})
        finally:
            probe_metadata.drop_all(db_engine, tables=[probe])
