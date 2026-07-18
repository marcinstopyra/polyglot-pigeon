"""Runnable Telegram bot prototype with a fully mocked backend.

This module stands up a *real* ``python-telegram-bot`` application so the
interaction design (commands, inline-keyboard multi-select, message
delivery) can be tried in Telegram before any real backend exists. There
is no IMAP, no LLM, and no database here: the news items and their
"learning" transforms are hardcoded German-B1 / English samples.

Run it with a BotFather token::

    export TELEGRAM_BOT_TOKEN="123456:abc..."
    export TELEGRAM_ALLOWED_USER_IDS="11111111"   # optional; empty = allow all
    PYTHONPATH=src python -m polyglot_pigeon.bot.mock_bot

Then message the bot: ``/start`` then ``/news``.
"""

import html
import logging
import os

from pydantic import Field
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from polyglot_pigeon.models.models import MyBaseModel

log = logging.getLogger(__name__)

# Telegram hard limit for a single text message.
TELEGRAM_MAX_CHARS = 4096
# Telegram truncates inline-button labels; keep them comfortably short.
BUTTON_LABEL_MAX = 48

# Callback-data prefixes for the inline keyboard.
CB_TOGGLE = "toggle:"
CB_DONE = "done"
CB_CLEAR = "clear"


# ── Mock data ─────────────────────────────────────────────────────────────────


class MockNewsItem(MyBaseModel):
    """A single hardcoded news item with its pre-generated learning content.

    Mirrors the fields of the real ``TargetArticle`` (title/source/date/
    content/glossary) so the delivery formatting is representative.
    """

    id: str
    title: str
    source: str
    date: str
    content: str
    glossary: dict[str, str] = Field(default_factory=dict)


MOCK_NEWS: list[MockNewsItem] = [
    MockNewsItem(
        id="pfand",
        title="Deutschland erweitert das Pfandsystem",
        source="Umwelt Heute",
        date="18. Juli 2026",
        content=(
            "Ab dem nächsten Jahr gibt es in Deutschland Pfand auf noch mehr "
            "Getränkeflaschen. Auch auf Flaschen mit Saft und Milch müssen die "
            "Kundinnen und Kunden dann 25 Cent bezahlen. Das Geld bekommt man "
            "zurück, wenn man die leere Flasche in den Supermarkt bringt. Die "
            "Regierung hofft, dass so weniger Plastik in der Natur landet. "
            "Viele Menschen finden die Idee gut, aber einige Geschäfte "
            "beklagen den zusätzlichen Aufwand."
        ),
        glossary={
            "das Pfand": "the deposit (refundable)",
            "die Getränkeflasche": "the drink bottle",
            "zurückbekommen": "to get back",
            "die Regierung": "the government",
            "der Aufwand": "the effort / hassle",
            "beklagen": "to complain about",
        },
    ),
    MockNewsItem(
        id="hitze",
        title="Rekordhitze im Süden Europas",
        source="Wetterjournal",
        date="18. Juli 2026",
        content=(
            "In Spanien, Italien und Griechenland ist es diese Woche extrem "
            "heiß. In einigen Städten steigt das Thermometer auf über 44 Grad. "
            "Die Behörden warnen vor allem ältere Menschen, mittags zu Hause "
            "zu bleiben. Viele Touristen besuchen Museen oder Schwimmbäder, um "
            "der Hitze zu entkommen. Fachleute sagen, dass solche Hitzewellen "
            "wegen des Klimawandels immer häufiger werden."
        ),
        glossary={
            "die Rekordhitze": "the record heat",
            "steigen": "to rise / climb",
            "die Behörde": "the authority (public body)",
            "entkommen": "to escape",
            "die Hitzewelle": "the heat wave",
            "der Klimawandel": "the climate change",
        },
    ),
    MockNewsItem(
        id="zug",
        title="Neue Nachtzug-Verbindung Berlin–Paris",
        source="Reise & Bahn",
        date="17. Juli 2026",
        content=(
            "Seit dieser Woche fährt wieder ein Nachtzug zwischen Berlin und "
            "Paris. Die Reise dauert etwa zwölf Stunden, und man kann in einem "
            "Bett schlafen. Viele Reisende finden den Zug bequemer und "
            "umweltfreundlicher als das Flugzeug. Die Tickets sind schnell "
            "ausverkauft, deshalb plant die Bahn schon weitere Verbindungen. "
            "Wer möchte, kann ein eigenes Abteil buchen."
        ),
        glossary={
            "der Nachtzug": "the night train",
            "die Reise": "the journey / trip",
            "bequem": "comfortable",
            "umweltfreundlich": "environmentally friendly",
            "ausverkauft": "sold out",
            "das Abteil": "the compartment",
        },
    ),
    MockNewsItem(
        id="fisch",
        title="Forscher entdecken neue Fischart",
        source="Wissen Kompakt",
        date="16. Juli 2026",
        content=(
            "Ein Team von Meeresforschern hat tief im Atlantik eine unbekannte "
            "Fischart gefunden. Der kleine Fisch lebt in mehr als 3000 Metern "
            "Tiefe, wo es völlig dunkel ist. Sein Körper leuchtet leicht "
            "blau, um andere Tiere anzulocken. Die Wissenschaftler waren "
            "überrascht, dass dort überhaupt Leben möglich ist. Nun wollen sie "
            "den Fisch genauer untersuchen."
        ),
        glossary={
            "der Forscher": "the researcher",
            "entdecken": "to discover",
            "die Tiefe": "the depth",
            "leuchten": "to glow / shine",
            "anlocken": "to attract / lure",
            "untersuchen": "to examine / study",
        },
    ),
    MockNewsItem(
        id="wahl",
        title="Estland wählt digital – ein Vorbild?",
        source="Politik Aktuell",
        date="15. Juli 2026",
        content=(
            "In Estland können die Menschen seit vielen Jahren über das "
            "Internet wählen. Man braucht nur einen Computer und einen "
            "besonderen Ausweis. Viele andere Länder schauen jetzt genau nach "
            "Estland, weil die Wahl dort schnell und sicher ist. Kritiker "
            "warnen aber vor Hackern und Betrug. Trotzdem sind die meisten "
            "Bürgerinnen und Bürger mit dem System zufrieden."
        ),
        glossary={
            "wählen": "to vote / elect",
            "der Ausweis": "the ID card",
            "das Vorbild": "the role model / example",
            "der Kritiker": "the critic",
            "der Betrug": "the fraud",
            "zufrieden": "satisfied / content",
        },
    ),
]

MOCK_NEWS_BY_ID: dict[str, MockNewsItem] = {item.id: item for item in MOCK_NEWS}


# ── Access control ────────────────────────────────────────────────────────────


def _allowed_user_ids() -> set[int]:
    """Parse the whitelist from ``TELEGRAM_ALLOWED_USER_IDS`` (comma separated).

    An empty/unset value means "allow everyone" — convenient for a prototype.
    """
    raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").strip()
    if not raw:
        return set()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            log.warning("Ignoring non-integer user id in whitelist: %r", part)
    return ids


def _is_authorized(update: Update, allowed: set[int]) -> bool:
    if not allowed:
        return True  # no whitelist configured → open (prototype only)
    user = update.effective_user
    return user is not None and user.id in allowed


# ── Formatting helpers ────────────────────────────────────────────────────────


def _selected_ids(context: ContextTypes.DEFAULT_TYPE) -> set[str]:
    """Per-user selection set, stored in ``context.user_data``."""
    return context.user_data.setdefault("selected", set())


def _button_label(item: MockNewsItem, selected: bool) -> str:
    check = "✅ " if selected else "▫️ "
    title = item.title
    room = BUTTON_LABEL_MAX - len(check)
    if len(title) > room:
        title = title[: room - 1].rstrip() + "…"
    return f"{check}{title}"


def _build_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                _button_label(item, item.id in selected),
                callback_data=f"{CB_TOGGLE}{item.id}",
            )
        ]
        for item in MOCK_NEWS
    ]
    action_row = [InlineKeyboardButton("✔️ Done", callback_data=CB_DONE)]
    if selected:
        action_row.insert(0, InlineKeyboardButton("✖️ Clear", callback_data=CB_CLEAR))
    rows.append(action_row)
    return InlineKeyboardMarkup(rows)


def _format_article(item: MockNewsItem) -> str:
    """Render one news item as Telegram-flavoured HTML.

    Uses ``html.escape`` on every dynamic part; Telegram supports a small
    subset of HTML tags (``<b>``, ``<i>``, ``<code>`` ...).
    """
    parts = [
        f"<b>{html.escape(item.title)}</b>",
        f"<i>{html.escape(item.source)} · {html.escape(item.date)}</i>",
        "",
        html.escape(item.content),
    ]
    if item.glossary:
        parts.append("")
        parts.append("—" * 8)
        for word, translation in item.glossary.items():
            parts.append(f"<b>{html.escape(word)}</b>: {html.escape(translation)}")
    return "\n".join(parts)


def _split_for_telegram(text: str, limit: int = TELEGRAM_MAX_CHARS) -> list[str]:
    """Split ``text`` into <=limit chunks, preferring paragraph boundaries."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        # A single paragraph longer than the limit: hard-wrap it.
        while len(paragraph) > limit:
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


# ── Handlers ──────────────────────────────────────────────────────────────────


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed: set[int] = context.bot_data["allowed_user_ids"]
    if not _is_authorized(update, allowed):
        log.info("Ignoring /start from unauthorized user %s", update.effective_user)
        return
    await update.message.reply_text(
        "🕊️ <b>PolyglotPigeon</b> (prototype)\n\n"
        "Send /news to see today's headlines, pick the ones you want, and "
        "I'll send you a German (B1) reading with an English glossary.\n\n"
        "<i>Backend is mocked — content is hardcoded sample data.</i>",
        parse_mode="HTML",
    )


async def news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed: set[int] = context.bot_data["allowed_user_ids"]
    if not _is_authorized(update, allowed):
        log.info("Ignoring /news from unauthorized user %s", update.effective_user)
        return
    _selected_ids(context).clear()
    await update.message.reply_text(
        "📰 <b>Available news</b>\nTap titles to select, then press <b>Done</b>:",
        parse_mode="HTML",
        reply_markup=_build_keyboard(set()),
    )


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed: set[int] = context.bot_data["allowed_user_ids"]
    query = update.callback_query
    if not _is_authorized(update, allowed):
        await query.answer("Not authorized.", show_alert=True)
        return

    selected = _selected_ids(context)
    data = query.data or ""

    if data.startswith(CB_TOGGLE):
        item_id = data[len(CB_TOGGLE) :]
        if item_id in MOCK_NEWS_BY_ID:
            if item_id in selected:
                selected.discard(item_id)
            else:
                selected.add(item_id)
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=_build_keyboard(selected))
        return

    if data == CB_CLEAR:
        selected.clear()
        await query.answer("Cleared.")
        await query.edit_message_reply_markup(reply_markup=_build_keyboard(selected))
        return

    if data == CB_DONE:
        if not selected:
            await query.answer("Select at least one article first.", show_alert=True)
            return
        await query.answer()
        picks = [item for item in MOCK_NEWS if item.id in selected]
        await query.edit_message_text(
            f"✍️ Preparing {len(picks)} reading(s)…", parse_mode="HTML"
        )
        await _deliver(update, context, picks)
        selected.clear()
        return

    await query.answer()


async def _deliver(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    picks: list[MockNewsItem],
) -> None:
    """Send the (mock) transformed learning content for each pick."""
    chat_id = update.effective_chat.id
    for item in picks:
        # Simulate the "transform on selection" latency of the real backend.
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        for chunk in _split_for_telegram(_format_article(item)):
            await context.bot.send_message(
                chat_id=chat_id, text=chunk, parse_mode="HTML"
            )
    await context.bot.send_message(
        chat_id=chat_id,
        text="✅ Done. Send /news for more.",
    )


# ── Entry point ───────────────────────────────────────────────────────────────


def build_application(token: str, allowed_user_ids: set[int]) -> Application:
    """Construct the bot application with handlers registered."""
    app = Application.builder().token(token).build()
    app.bot_data["allowed_user_ids"] = allowed_user_ids
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("news", news))
    app.add_handler(CallbackQueryHandler(on_button))
    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is not set. Get a token from @BotFather and:\n"
            "  export TELEGRAM_BOT_TOKEN='123456:abc...'"
        )

    allowed = _allowed_user_ids()
    if allowed:
        log.info("Whitelist active for user ids: %s", sorted(allowed))
    else:
        log.warning(
            "No TELEGRAM_ALLOWED_USER_IDS set — the bot will respond to ANYONE. "
            "Set it for a real whitelist."
        )

    app = build_application(token, allowed)
    log.info("Starting mock bot (long polling). Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
