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

    Storage is second-precision `DATETIME`. Sub-second components are
    truncated in Python rather than left to MySQL, which *rounds* them:
    `09:30:00.6` would become `09:30:01`, a timestamp in the future.
    Truncating always errs backwards, which is the safe direction for
    "has this been processed yet" comparisons.
    """

    impl = DATETIME()
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
        return value.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)
