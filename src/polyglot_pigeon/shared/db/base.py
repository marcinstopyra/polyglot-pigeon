from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, declared_attr

# Stable, nameable constraint/index names so Alembic autogenerate can emit
# DROP/RENAME operations against them later.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

TABLE_ARGS = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in the project."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    @declared_attr.directive
    def __table_args__(cls) -> dict:  # noqa: N805
        # Applied to every mapped subclass automatically, so a table can't be
        # added without utf8mb4 by forgetting to repeat this by hand.
        return dict(TABLE_ARGS)
