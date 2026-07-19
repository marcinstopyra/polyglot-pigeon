"""Runnable Telegram bot prototype with a fully mocked backend.

This module stands up a *real* ``python-telegram-bot`` application so the
interaction design (commands, inline-keyboard multi-select, message
delivery) can be tried in Telegram before any real backend exists. There
is no IMAP, no LLM, and no database here: the news items and their
"learning" transforms are hardcoded German-B1 / English samples.

Configure ``telegram.token`` and ``telegram.whitelisted_users`` in the same
config file the rest of the app uses, then run::

    PYTHONPATH=src python -m polyglot_pigeon.bot.mock_bot -c config.yaml

Then open the bot and press START — everything after that is button-driven.
"""

import argparse
import asyncio
import html
import logging
import random
from enum import Enum
from pathlib import Path

from pydantic import Field
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from polyglot_pigeon.config import ConfigLoader, get_config
from polyglot_pigeon.models.configurations import Language
from polyglot_pigeon.models.models import MyBaseModel

log = logging.getLogger(__name__)

# Telegram hard limit for a single text message.
TELEGRAM_MAX_CHARS = 4096
# Max inline-button label length (Telegram's limit); long labels wrap onto
# multiple lines, which is fine for full news titles.
BUTTON_LABEL_MAX = 64

# Callback-data prefixes for the inline keyboard.
CB_TOGGLE = "toggle:"
CB_DONE = "done"
CB_CLEAR = "clear"
CB_NEWS = "news"
CB_LANG = "lang:"
CB_SETTINGS = "settings"
CB_MENU = "menu"

# Simulated LLM generation latency (seconds) before the digest is delivered.
LLM_DELAY_MIN_S = 4.0
LLM_DELAY_MAX_S = 8.0


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
        id="ukraine",
        title="Ukraine entlässt Verteidigungsminister Fedorov – Proteste und Chaos",
        source="The Kyiv Independent (War Notes)",
        date="17. Juli 2026",
        content=(
            "Der ukrainische Präsident Selenskyj hat den Reform-"
            "Verteidigungsminister Fedorov entlassen, und zwar nur sechs "
            "Monate nach seiner Ernennung. Fedorov hatte mutige Reformen "
            "vorgeschlagen, wie höhere Gehälter und feste Verträge für "
            "Soldaten, aber das Militär war nicht begeistert. Tausende "
            "Menschen haben in Kiew und anderen Städten protestiert, weil sie "
            "Fedorovs Entlassung unfair finden. Fedorov behauptet, dass der "
            "Armeechef Syrskyi ihm ein Ultimatum gestellt hat, und ein "
            "Berater hat Syrskyi sogar beschuldigt, „Friendly Fire“-Vorfälle "
            "zu vertuschen. Die neue Verteidigungsministerin ist jetzt die "
            "kommissarische Leiterin des Sicherheitsdienstes, aber ob das gut "
            "geht, ist fraglich. Vielleicht hätte Fedorov einfach mehr Zeit "
            "gebraucht, um die Armee zu ent-sowjetisieren. Aber wer braucht "
            "schon Reformen, wenn man Krieg führt?"
        ),
        glossary={
            "entlassen": "fired / dismissed",
            "die Ernennung": "appointment",
            "die Reformen": "reforms",
            "die Gehälter": "salaries",
            "festen Verträge": "fixed-term contracts",
            "die Entlassung": "dismissal",
            "das Ultimatum": "ultimatum",
            "der Berater": "advisor",
            "vertuschen": "to cover up",
            "die Friendly Fire-Vorfälle": "friendly fire incidents",
            "die kommissarische Leiterin": "acting head",
        },
    ),
    MockNewsItem(
        id="iran",
        title="USA und Iran eskalieren – Kuwait bekommt Ärger mit dem Wasser",
        source="FP's Alexandra Sharp (World Brief)",
        date="17. Juli 2026",
        content=(
            "Die USA und der Iran liefern sich eine neue Runde von Angriffen, "
            "und diesmal sind auch Brücken und Bahnhöfe in Iran betroffen. Der "
            "Iran hat daraufhin US-Stützpunkte in Bahrain, Kuwait und Katar "
            "angegriffen, aber das wirklich Lustige ist, dass eine "
            "Entsalzungsanlage in Kuwait getroffen wurde. 90 Prozent des "
            "Trinkwassers in Kuwait kommt aus Entsalzung, also haben die jetzt "
            "ein echtes Problem. Der US-Präsident Trump sagt, die USA "
            "gewinnen, aber die Ölpreise steigen, weil die Straße von Hormus "
            "blockiert ist. Vielleicht wäre ein Waffenstillstand doch eine "
            "gute Idee, aber wer will schon Frieden, wenn man sich gegenseitig "
            "bombardieren kann?"
        ),
        glossary={
            "eskalieren": "to escalate",
            "die Angriffe": "attacks",
            "die Brücken": "bridges",
            "die Bahnhöfe": "train stations",
            "die Entsalzungsanlage": "desalination plant",
            "das Trinkwasser": "drinking water",
            "die Ölpreise": "oil prices",
            "die Straße von Hormus": "Strait of Hormuz",
            "der Waffenstillstand": "ceasefire",
        },
    ),
    MockNewsItem(
        id="uk",
        title="Großbritannien bekommt einen neuen Premier – wieder mal",
        source="FP's Alexandra Sharp (World Brief)",
        date="17. Juli 2026",
        content=(
            "Großbritannien hat einen neuen Labour-Chef gewählt: Andy Burnham, "
            "der frühere Bürgermeister von Manchester. Er wird König Charles "
            "III. bitten, eine Regierung zu bilden, und das ist der siebte "
            "Premier seit 2016. Die Labour-Partei hat mit Skandalen zu "
            "kämpfen, und die rechte Reform UK-Partei ist in den Umfragen "
            "stark. Burnham verspricht große Wirtschaftsreformen, aber ob das "
            "reicht, um die Leute zu überzeugen? Wahrscheinlich nicht, aber "
            "zumindest gibt es jetzt einen neuen Namen, den man sich merken "
            "muss."
        ),
        glossary={
            "der Premier": "prime minister",
            "der Bürgermeister": "mayor",
            "die Regierung bilden": "to form a government",
            "die Skandale": "scandals",
            "die Umfragen": "polls",
            "die Wirtschaftsreformen": "economic reforms",
        },
    ),
    MockNewsItem(
        id="china",
        title="China bestreitet Einmischung in US-Wahlen – Trump spinnt weiter",
        source="FP's Alexandra Sharp (World Brief)",
        date="17. Juli 2026",
        content=(
            "China hat bestritten, sich in die US-Wahl 2020 eingemischt zu "
            "haben, nachdem Trump wieder einmal Verschwörungstheorien "
            "verbreitet hat. Trump behauptet, China habe 220 Millionen US-"
            "Wählerdaten gestohlen, aber diese Daten sind öffentlich und "
            "können gekauft werden. Ein Geheimdienstbericht aus dem Jahr 2021 "
            "hat bereits festgestellt, dass China die Daten gesammelt hat, um "
            "den Wahlausgang vorherzusagen, nicht um ihn zu manipulieren. "
            "Experten sagen, Trump will nur Zweifel an den Wahlen säen, weil "
            "seine Umfragewerte im Keller sind. Aber wer braucht schon Fakten, "
            "wenn man eine gute Geschichte hat?"
        ),
        glossary={
            "bestreiten": "to deny",
            "die Einmischung": "interference",
            "die Verschwörungstheorien": "conspiracy theories",
            "die Wählerdaten": "voter data",
            "der Geheimdienstbericht": "intelligence report",
            "den Wahlausgang vorhersagen": "to predict the election outcome",
            "manipulieren": "to manipulate",
            "Zweifel säen": "to sow doubt",
            "die Umfragewerte": "poll numbers",
        },
    ),
    MockNewsItem(
        id="japan",
        title="Japan: Nur Männer dürfen Kaiser werden – das wird lustig",
        source="FP's Alexandra Sharp (World Brief)",
        date="17. Juli 2026",
        content=(
            "Das japanische Parlament hat ein Gesetz verabschiedet, das nur "
            "Männern erlaubt, Kaiser zu werden. Das Problem: Von 16 "
            "erwachsenen Mitgliedern der kaiserlichen Familie sind nur fünf "
            "Männer. Prinzessin Aiko ist sehr beliebt, aber sie darf nicht auf "
            "den Thron. Stattdessen will die Regierung entfernte männliche "
            "Verwandte adoptieren, um die Thronfolge zu sichern. Feministinnen "
            "nennen das „Zuchtstuten-Politik“, und sie haben wahrscheinlich "
            "recht. Aber hey, Tradition ist Tradition, auch wenn sie dumm ist."
        ),
        glossary={
            "das Gesetz verabschieden": "to pass a law",
            "der Kaiser": "emperor",
            "die kaiserliche Familie": "imperial family",
            "die Thronfolge": "succession to the throne",
            "entfernte Verwandte": "distant relatives",
            "adoptieren": "to adopt",
            "die Feministinnen": "feminists",
            "die Zuchtstuten-Politik": "breeding mare policy",
        },
    ),
    MockNewsItem(
        id="fussball",
        title="Fußballgeschichte: Wie die Briten den Rest der Welt das Kicken lehrten",
        source="Histories",
        date="18. Juli 2026",
        content=(
            "In dieser Ausgabe von Histories geht es um die Entstehung des "
            "modernen Fußballs. Im 19. Jahrhundert spielten englische "
            "Privatschulen verschiedene Versionen von „Football“, aber erst in "
            "Cambridge wurden die Regeln vereinheitlicht. Der Fußballverband "
            "(FA) wurde 1863 gegründet, und die FA-Cup-Regeln verbreiteten "
            "sich weltweit durch britische Expatriates. In Brasilien brachte "
            "Charles Miller das Spiel, in Italien gründeten Briten den AC "
            "Mailand, und in Argentinien halfen britische Lehrer, die "
            "nationale Liga aufzubauen. Ohne die Briten gäbe es vielleicht "
            "keinen Fußball, wie wir ihn kennen – oder vielleicht wäre es "
            "einfach Rugby geworden."
        ),
        glossary={
            "die Entstehung": "origin / emergence",
            "die Privatschulen": "private schools",
            "die Regeln vereinheitlichen": "to unify the rules",
            "der Fußballverband": "football association",
            "sich verbreiten": "to spread",
            "die Expatriates": "expatriates",
            "die nationale Liga": "national league",
            "aufbauen": "to build / establish",
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
    BTN_BACK = "btn_back"
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

# Map the config's Language enum to the 2-letter codes used by the catalog.
_LANGUAGE_CODES: dict[Language, str] = {
    Language.ENGLISH: "en",
    Language.GERMAN: "de",
    Language.RUSSIAN: "ru",
    Language.ITALIAN: "it",
    Language.SPANISH: "es",
    Language.TURKISH: "tr",
    Language.POLISH: "pl",
}

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
        MessageKey.BTN_BACK: "⬅️ Zurück",
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
        MessageKey.BTN_BACK: "⬅️ Back",
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


def _post_delivery_markup(messages: "MessageCatalog") -> InlineKeyboardMarkup:
    """Actions offered after a delivery: pick more news, or go back to the menu."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    messages.get(MessageKey.BTN_SHOW_NEWS), callback_data=CB_NEWS
                )
            ],
            [
                InlineKeyboardButton(
                    messages.get(MessageKey.BTN_BACK), callback_data=CB_MENU
                )
            ],
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
    rows.append(
        [InlineKeyboardButton(messages.get(MessageKey.BTN_BACK), callback_data=CB_MENU)]
    )
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


async def _send_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Post the entry menu (language picker + settings) in the known language."""
    known = _known_messages(context)
    await context.bot.send_message(
        chat_id=chat_id,
        text=known.get(MessageKey.MENU_HEADER),
        parse_mode="HTML",
        reply_markup=_menu_markup(known),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed: set[int] = context.bot_data["allowed_user_ids"]
    if not _is_authorized(update, allowed):
        log.info("Ignoring /start from unauthorized user %s", update.effective_user)
        return
    await _send_menu(update.effective_chat.id, context)


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

    if data == CB_MENU:
        await query.answer()
        await _send_menu(update.effective_chat.id, context)
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

    # Simulate the LLM generating the whole digest (intro + per-article
    # transforms) before anything is delivered.
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(random.uniform(LLM_DELAY_MIN_S, LLM_DELAY_MAX_S))

    # Intro is generated after the articles are chosen/processed, shown first.
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
        reply_markup=_post_delivery_markup(messages),
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
    parser = argparse.ArgumentParser(
        description="PolyglotPigeon Telegram bot prototype"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        required=True,
        help="Path to the configuration file",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    args = parser.parse_args()

    ConfigLoader().load(config_path=str(args.config))
    config = get_config()

    level = (
        logging.DEBUG
        if args.verbose
        else getattr(logging, config.logging.level.upper(), logging.INFO)
    )
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if config.telegram is None:
        raise SystemExit(
            "No 'telegram' section in the config. Add telegram.token and "
            "telegram.whitelisted_users (see config.example.yaml)."
        )
    if not config.telegram.token:
        raise SystemExit("telegram.token is empty — set your @BotFather token.")

    whitelist = set(config.telegram.whitelisted_users)
    known_language = _LANGUAGE_CODES.get(config.language.known, KNOWN_LANGUAGE)

    if whitelist:
        log.info("Whitelist active for user ids: %s", sorted(whitelist))
    else:
        log.warning(
            "telegram.whitelisted_users is empty — the bot will respond to "
            "ANYONE. Set it for a real whitelist."
        )

    app = build_application(
        config.telegram.token, whitelist, known_language=known_language
    )
    log.info("Starting Telegram bot prototype (long polling). Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
