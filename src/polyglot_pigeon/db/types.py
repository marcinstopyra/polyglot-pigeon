from datetime import datetime, timezone

from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """The one datetime type every model in this project must use.

    `DateTime(timezone=True)` is a silent no-op on MySQL: the dialect
    accepts the flag but emits plain `DATETIME`, and the driver returns
    naive datetimes regardless. This decorator is what actually enforces
    an aware-UTC boundary — don't "simplify" it into `DateTime(timezone=True)`.

    Storage is `DATETIME(6)`: MySQL's default is whole seconds *with
    rounding*, and this project ties ordering decisions to microsecond
    granularity.
    """

    impl = DATETIME(fsp=6)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "UtcDateTime requires a timezone-aware datetime, got a naive "
                f"value: {value!r}"
            )
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)
