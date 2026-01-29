"""Scheduler module for email processing."""

from polyglot_pigeon.scheduler.pipeline import (
    EmailProcessingPipeline,
    Pipeline,
    PlaceholderPipeline,
    ProcessingResult,
)
from polyglot_pigeon.scheduler.scheduler import EmailScheduler

__all__ = [
    "EmailProcessingPipeline",
    "EmailScheduler",
    "Pipeline",
    "PlaceholderPipeline",
    "ProcessingResult",
]
