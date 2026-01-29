# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PolyglotPigeon is a Python-based email language learning assistant that transforms newsletters into language learning content.

### Workflow

1. **Source email monitoring** - Newsletters arrive at a source email inbox (IMAP)
2. **Scheduled processing** - A scheduler controls when emails are processed; processed emails are marked with tags/labels or read status
3. **LLM transformation** - Newsletter content is sent to an LLM API (Claude, Perplexity, or OpenAI) to generate learning content
4. **Delivery** - Final newsletter is sent to user's target email (SMTP)

### Language Configuration

Users configure:
- `known_language` - User's native/fluent language (for translations)
- `target_language` - Language being learned
- `target_language_level` - CEFR level (A1-C2) determining complexity

### Output Email Structure

```
# Title
<static title, not dependent on specific issue content>

<Introduction: journalistic intro to the news listed below - generated last since it depends on article content>

## Articles:
<Each article is 4-8 sentences in target_language at target_language_level>

---
**<word/phrase in target_language>**: <translation to known_language>
**<word/phrase in target_language>**: <translation to known_language>
...

<next article>

---
<glossary for that article>
```

The glossary under each article contains words/phrases that may be unfamiliar to a learner at the configured level.

## Development Commands

```bash
# Install dependencies
poetry install

# Format code and auto-fix issues
make format

# Check linting (no modifications)
make lint

# Run tests
poetry run pytest

# Run a single test file
poetry run pytest tests/unit_tests/test_config.py

# Run a specific test
poetry run pytest tests/unit_tests/test_config.py::test_function_name

# Run application
poetry run python src/polyglot_pigeon/main.py -c config.yaml [-v]
```

## Architecture

**Source layout:** `src/polyglot_pigeon/`

The project follows a **simple modules pattern** - code is organized by feature/domain rather than technical layers:

```
src/polyglot_pigeon/
├── mail/            # Email handling (IMAP reading, SMTP sending)
│   ├── __init__.py  # Note: named 'mail' to avoid collision with stdlib 'email'
│   └── reader.py    # EmailReader class
├── llm/             # LLM API integrations
│   ├── __init__.py
│   ├── client.py    # LLMClient ABC + Claude/OpenAI/Perplexity clients
│   └── models.py    # LLMMessage, LLMResponse models
├── scheduler/       # Email processing scheduler
│   ├── __init__.py
│   ├── scheduler.py # EmailScheduler class
│   └── pipeline.py  # Pipeline ABC + processing implementations
├── models/          # Pydantic data models
│   ├── models.py    # Base models (MyBaseModel, Email)
│   └── configurations.py  # Config models
├── config.py        # ConfigLoader singleton
└── main.py          # CLI entry point
```

**Core components:**
- **config.py** - Singleton `ConfigLoader` for YAML configuration with caching and reload
- **models/models.py** - `MyBaseModel` with custom enum parsing (case-insensitive) and serialization; `Email` model for email data
- **models/configurations.py** - All config dataclasses: `SourceEmailConfig`, `TargetEmailConfig`, `LLMConfig`, `LanguageConfig`, `ScheduleConfig`, `LoggingConfig`
- **mail/reader.py** - `EmailReader` class for IMAP operations (fetch, mark as read, add labels)
- **llm/client.py** - `LLMClient` ABC with `ClaudeClient`, `OpenAIClient`, `PerplexityClient` implementations
- **scheduler/scheduler.py** - `EmailScheduler` for cron-like scheduled email processing
- **scheduler/pipeline.py** - `Pipeline` ABC for email processing workflows

**Configuration:** Copy `src/polyglot_pigeon/config.example.yaml` to `config.yaml` (gitignored) for local development.

## Code Style

- Python 3.12+
- Ruff for linting and formatting (88 char line length, double quotes)
- Pydantic v2 for data validation
- Type hints throughout
