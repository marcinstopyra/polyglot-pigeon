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

Then open the bot and press START — everything after that is button-driven.
"""

import html
import logging
import os
from enum import Enum

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
CB_NEWS = "news"
CB_LANG = "lang:"
CB_SETTINGS = "settings"


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


# ── Learning languages (mock) ─────────────────────────────────────────────────
#
# A user can have several languages assigned. Only German is wired up; the
# others exist to show the multi-language entry point. ``label`` is written in
# the language itself (never translated); the surrounding menu chrome is shown
# in the user's *known* language.


class LearningOption(MyBaseModel):
    """One language/level a user can practise from the entry menu."""

    code: str  # language code used to resolve content + UI (e.g. "de")
    label: str  # display name in its own language, e.g. "Deutsch B1"
    emoji: str
    implemented: bool = False


LEARNING_OPTIONS: list[LearningOption] = [
    LearningOption(code="de", label="Deutsch B1", emoji="🥨", implemented=True),
    LearningOption(code="ru", label="Русский C1", emoji="🪆", implemented=False),
]
LEARNING_OPTIONS_BY_CODE: dict[str, LearningOption] = {
    o.code: o for o in LEARNING_OPTIONS
}


# ── System messages (i18n) ────────────────────────────────────────────────────
#
# Every UI string has a key; ``MessageCatalog.get`` resolves key + language to
# text. Here the catalog is backed by a hardcoded dict, but that ``get`` is
# exactly the "fetch the translation by key" the real backend will do against a
# SQL ``ui_message(key, lang, text)`` table — so swapping the backing store
# leaves every call site unchanged.
#
# Two languages are in play: the entry menu / settings are shown in the user's
# *known* language, while the news-reading flow is shown in the *target*
# (learning) language they picked.


class MessageKey(Enum):
    """Stable keys for the bot's UI strings (never shown to the user)."""

    MENU_HEADER = "menu_header"
    BTN_SETTINGS = "btn_settings"
    NOT_IMPLEMENTED = "not_implemented"
    NEWS_LIST_HEADER = "news_list_header"
    BTN_SHOW_NEWS = "btn_show_news"
    BTN_DONE = "btn_done"
    BTN_CLEAR = "btn_clear"
    PREPARING = "preparing"
    DONE = "done"
    SELECT_AT_LEAST_ONE = "select_at_least_one"
    NOT_AUTHORIZED = "not_authorized"
    CLEARED = "cleared"


# Known language: the user's own language (menu/settings chrome).
KNOWN_LANGUAGE = "en"
# Default learning language when none has been picked yet.
DEFAULT_LEARNING_LANGUAGE = "de"
FALLBACK_LANGUAGE = "en"

_TRANSLATIONS: dict[str, dict[MessageKey, str]] = {
    "de": {
        MessageKey.MENU_HEADER: (
            "🕊️ <b>PolyglotPigeon</b> (Prototyp)\n\n"
            "Was möchtest du üben? Wähle eine Sprache oder öffne die "
            "Einstellungen.\n\n"
            "<i>Das Backend ist simuliert — die Inhalte sind fest hinterlegte "
            "Beispieldaten.</i>"
        ),
        MessageKey.BTN_SETTINGS: "⚙️ Einstellungen",
        MessageKey.NOT_IMPLEMENTED: "🚧 Noch nicht implementiert.",
        MessageKey.NEWS_LIST_HEADER: (
            "📰 <b>Verfügbare Nachrichten</b>\n"
            "Tippen Sie auf die Titel zum Auswählen und dann auf <b>Fertig</b>:"
        ),
        MessageKey.BTN_SHOW_NEWS: "📰 Nachrichten anzeigen",
        MessageKey.BTN_DONE: "✔️ Fertig",
        MessageKey.BTN_CLEAR: "✖️ Leeren",
        MessageKey.PREPARING: "✍️ Ich bereite {count} Lesetext(e) vor …",
        MessageKey.DONE: "✅ Fertig.",
        MessageKey.SELECT_AT_LEAST_ONE: (
            "Bitte wählen Sie zuerst mindestens einen Artikel aus."
        ),
        MessageKey.NOT_AUTHORIZED: "Kein Zugriff.",
        MessageKey.CLEARED: "Auswahl geleert.",
    },
    "en": {
        MessageKey.MENU_HEADER: (
            "🕊️ <b>PolyglotPigeon</b> (prototype)\n\n"
            "What would you like to practise? Pick a language below, or open "
            "settings.\n\n"
            "<i>Backend is mocked — content is hardcoded sample data.</i>"
        ),
        MessageKey.BTN_SETTINGS: "⚙️ Settings",
        MessageKey.NOT_IMPLEMENTED: "🚧 Not implemented yet.",
        MessageKey.NEWS_LIST_HEADER: (
            "📰 <b>Available news</b>\nTap titles to select, then press <b>Done</b>:"
        ),
        MessageKey.BTN_SHOW_NEWS: "📰 Show news",
        MessageKey.BTN_DONE: "✔️ Done",
        MessageKey.BTN_CLEAR: "✖️ Clear",
        MessageKey.PREPARING: "✍️ Preparing {count} reading(s) …",
        MessageKey.DONE: "✅ Done.",
        MessageKey.SELECT_AT_LEAST_ONE: "Select at least one article first.",
        MessageKey.NOT_AUTHORIZED: "Not authorized.",
        MessageKey.CLEARED: "Cleared.",
    },
}


class MessageCatalog:
    """Resolves UI message keys to text in a chosen language.

    Mock stand-in for a SQL-backed ``ui_message(key, lang, text)`` table:
    ``get`` is the "fetch translation by key" the real backend will perform.
    """

    def __init__(
        self,
        language: str = DEFAULT_LEARNING_LANGUAGE,
        fallback: str = FALLBACK_LANGUAGE,
    ) -> None:
        self.language = language
        self.fallback = fallback

    def get(self, key: MessageKey, **params: object) -> str:
        table = _TRANSLATIONS.get(self.language, {})
        text = table.get(key) or _TRANSLATIONS[self.fallback][key]
        return text.format(**params) if params else text


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


def _menu_markup(known: "MessageCatalog") -> InlineKeyboardMarkup:
    """Entry menu: one button per learning language, plus settings.

    Language labels are shown in their own language; the settings label is in
    the user's known language.
    """
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                f"{option.emoji} {option.label}",
                callback_data=f"{CB_LANG}{option.code}",
            )
        ]
        for option in LEARNING_OPTIONS
    ]
    rows.append(
        [
            InlineKeyboardButton(
                known.get(MessageKey.BTN_SETTINGS), callback_data=CB_SETTINGS
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def _show_news_markup(messages: "MessageCatalog") -> InlineKeyboardMarkup:
    """A single button that opens the news list (used instead of typing /news)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    messages.get(MessageKey.BTN_SHOW_NEWS), callback_data=CB_NEWS
                )
            ]
        ]
    )


def _build_keyboard(
    selected: set[str], messages: "MessageCatalog"
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                _button_label(item, item.id in selected),
                callback_data=f"{CB_TOGGLE}{item.id}",
            )
        ]
        for item in MOCK_NEWS
    ]
    action_row = [
        InlineKeyboardButton(messages.get(MessageKey.BTN_DONE), callback_data=CB_DONE)
    ]
    if selected:
        action_row.insert(
            0,
            InlineKeyboardButton(
                messages.get(MessageKey.BTN_CLEAR), callback_data=CB_CLEAR
            ),
        )
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


def _generate_intro(picks: list[MockNewsItem]) -> str:
    """Return a journalistic intro summarising the chosen articles (German).

    Mock stand-in for ``TargetEmailContent.introduction``, which the real
    pipeline writes with the LLM *last* — after the articles are chosen and
    processed — so it can actually describe their content. For now it returns
    a fixed sample paragraph.
    """
    return (
        "Diese Woche gibt es viel zu besprechen: Die Ukraine entlässt ihren "
        "Reform-Verteidigungsminister, der Iran und die USA liefern sich eine "
        "neue Runde von Angriffen, und währenddessen eröffnet Chipotle sein "
        "erstes Restaurant in Mexiko. Außerdem: die besten Sommerbücher und "
        "eine Geschichtsstunde über die wahren Ursprünge des Fußballs. Alles "
        "brennt, aber wir haben Popcorn."
    )


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


def _known_messages(context: ContextTypes.DEFAULT_TYPE) -> "MessageCatalog":
    """Catalog for the user's known language (entry menu / settings chrome)."""
    return MessageCatalog(language=context.bot_data["known_language"])


def _learning_messages(context: ContextTypes.DEFAULT_TYPE) -> "MessageCatalog":
    """Catalog for the active learning language (the news-reading flow)."""
    lang = context.user_data.get("learning_language", DEFAULT_LEARNING_LANGUAGE)
    return MessageCatalog(language=lang)


async def _send_news_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset the selection and post the multi-select news list."""
    messages = _learning_messages(context)
    _selected_ids(context).clear()
    await context.bot.send_message(
        chat_id=chat_id,
        text=messages.get(MessageKey.NEWS_LIST_HEADER),
        parse_mode="HTML",
        reply_markup=_build_keyboard(set(), messages),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed: set[int] = context.bot_data["allowed_user_ids"]
    if not _is_authorized(update, allowed):
        log.info("Ignoring /start from unauthorized user %s", update.effective_user)
        return
    known = _known_messages(context)
    await update.message.reply_text(
        known.get(MessageKey.MENU_HEADER),
        parse_mode="HTML",
        reply_markup=_menu_markup(known),
    )


async def news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed: set[int] = context.bot_data["allowed_user_ids"]
    if not _is_authorized(update, allowed):
        log.info("Ignoring /news from unauthorized user %s", update.effective_user)
        return
    await _send_news_list(update.effective_chat.id, context)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed: set[int] = context.bot_data["allowed_user_ids"]
    query = update.callback_query
    known = _known_messages(context)
    if not _is_authorized(update, allowed):
        await query.answer(known.get(MessageKey.NOT_AUTHORIZED), show_alert=True)
        return

    selected = _selected_ids(context)
    data = query.data or ""

    if data.startswith(CB_LANG):
        code = data[len(CB_LANG) :]
        option = LEARNING_OPTIONS_BY_CODE.get(code)
        if option is None:
            await query.answer()
            return
        if not option.implemented:
            await query.answer()
            await query.message.reply_text(known.get(MessageKey.NOT_IMPLEMENTED))
            return
        context.user_data["learning_language"] = code
        await query.answer()
        await _send_news_list(update.effective_chat.id, context)
        return

    if data == CB_SETTINGS:
        await query.answer()
        await query.message.reply_text(known.get(MessageKey.NOT_IMPLEMENTED))
        return

    # From here on we are inside a learning session → learning-language UI.
    messages = _learning_messages(context)

    if data == CB_NEWS:
        await query.answer()
        await _send_news_list(update.effective_chat.id, context)
        return

    if data.startswith(CB_TOGGLE):
        item_id = data[len(CB_TOGGLE) :]
        if item_id in MOCK_NEWS_BY_ID:
            if item_id in selected:
                selected.discard(item_id)
            else:
                selected.add(item_id)
        await query.answer()
        await query.edit_message_reply_markup(
            reply_markup=_build_keyboard(selected, messages)
        )
        return

    if data == CB_CLEAR:
        selected.clear()
        await query.answer(messages.get(MessageKey.CLEARED))
        await query.edit_message_reply_markup(
            reply_markup=_build_keyboard(selected, messages)
        )
        return

    if data == CB_DONE:
        if not selected:
            await query.answer(
                messages.get(MessageKey.SELECT_AT_LEAST_ONE), show_alert=True
            )
            return
        await query.answer()
        picks = [item for item in MOCK_NEWS if item.id in selected]
        await query.edit_message_text(
            messages.get(MessageKey.PREPARING, count=len(picks)), parse_mode="HTML"
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
    messages = _learning_messages(context)
    chat_id = update.effective_chat.id

    # Intro is generated after the articles are chosen/processed, shown first.
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await context.bot.send_message(
        chat_id=chat_id, text=_generate_intro(picks), parse_mode="HTML"
    )

    for item in picks:
        # Simulate the "transform on selection" latency of the real backend.
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        for chunk in _split_for_telegram(_format_article(item)):
            await context.bot.send_message(
                chat_id=chat_id, text=chunk, parse_mode="HTML"
            )
    await context.bot.send_message(
        chat_id=chat_id,
        text=messages.get(MessageKey.DONE),
        reply_markup=_show_news_markup(messages),
    )


# ── Entry point ───────────────────────────────────────────────────────────────


def build_application(
    token: str,
    allowed_user_ids: set[int],
    known_language: str = KNOWN_LANGUAGE,
) -> Application:
    """Construct the bot application with handlers registered."""
    app = Application.builder().token(token).build()
    app.bot_data["allowed_user_ids"] = allowed_user_ids
    app.bot_data["known_language"] = known_language
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
