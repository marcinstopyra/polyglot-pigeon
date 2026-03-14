import logging

import pytest

from polyglot_pigeon.main import setup_logger


@pytest.fixture(autouse=True)
def reset_root_logger():
    """Close and remove any handlers added by setup_logger after each test."""
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        handler.close()
        root.removeHandler(handler)


def test_setup_logger_console_only():
    setup_logger(level=logging.INFO)
    root = logging.getLogger()
    assert root.level == logging.INFO
    assert len(root.handlers) == 1
    assert not isinstance(root.handlers[0], logging.FileHandler)


def test_setup_logger_with_file_creates_directory(tmp_path):
    log_file = tmp_path / "nested" / "app.log"
    setup_logger(level=logging.INFO, log_file=log_file)
    assert log_file.parent.exists()


def test_setup_logger_with_file_adds_file_handler(tmp_path):
    log_file = tmp_path / "app.log"
    setup_logger(level=logging.INFO, log_file=log_file)
    root = logging.getLogger()
    handler_types = [type(h) for h in root.handlers]
    assert logging.FileHandler in handler_types
    assert logging.StreamHandler in handler_types


def test_setup_logger_writes_to_file(tmp_path):
    log_file = tmp_path / "app.log"
    setup_logger(level=logging.INFO, log_file=log_file)
    logging.getLogger("test").info("hello from test")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert "hello from test" in log_file.read_text()


def test_setup_logger_debug_level():
    setup_logger(level=logging.DEBUG)
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logger_suppresses_noisy_loggers():
    setup_logger()
    for name in ("httpx", "httpcore", "anthropic", "openai"):
        assert logging.getLogger(name).level == logging.WARNING
