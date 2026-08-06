from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from polyglot_pigeon.shared.config import DatabaseSettings
from polyglot_pigeon.shared.db.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The single Alembic tree covers every model registered on the shared Base;
# `sqlalchemy.url` in alembic.ini is a placeholder overridden below with the
# same environment-derived settings the application itself uses.
target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", DatabaseSettings().url)

# `user_module_prefix` is what makes autogenerate render `pp.UtcDateTime()`
# instead of falling back to the type's raw DATETIME impl — see
# migrations/script.py.mako for the matching import.
USER_MODULE_PREFIX = "pp."


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        user_module_prefix=USER_MODULE_PREFIX,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            user_module_prefix=USER_MODULE_PREFIX,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
