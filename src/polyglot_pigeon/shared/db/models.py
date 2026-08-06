from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from polyglot_pigeon.shared.db.base import Base


class Language(Base):
    """A supported language. Supersedes the old `Language` enum (PP-05).

    `code` is a natural primary key rather than a surrogate int — the set is
    small and stable, and it keeps `es` / `pl` legible in queries and logs
    without a join (architecture doc §6). `String(8)` rather than the ISO
    639-1 minimum of 2 characters, so a regional variant can be expressed as
    `<language_code>-<country_code>` (e.g. `pt-br`) without a later migration
    to widen the column — see the PP-05 issue discussion.
    """

    __tablename__ = "languages"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name_en: Mapped[str] = mapped_column(String(64))
    name_native: Mapped[str] = mapped_column(String(64))
