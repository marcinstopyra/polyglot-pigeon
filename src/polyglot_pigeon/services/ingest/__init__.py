"""Ingest service: fetches source emails and prepares them for processing."""

from polyglot_pigeon.services.ingest.chunker import chunk_email
from polyglot_pigeon.services.ingest.cleaner import ContentCleaner
from polyglot_pigeon.services.ingest.reader import EmailReader

__all__ = ["ContentCleaner", "EmailReader", "chunk_email"]
