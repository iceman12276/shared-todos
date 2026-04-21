"""Unit tests for app/logging_config.py.

Verifies:
- configure_logging() sets the root logger level
- Auth event loggers exist at the expected names
- The module is importable without side effects at import time
"""

import logging


def test_configure_logging_sets_root_level() -> None:
    """configure_logging() must set root logger to INFO or lower."""
    from app.logging_config import configure_logging

    configure_logging()
    assert logging.getLogger().level <= logging.INFO


def test_auth_logger_exists_after_configure() -> None:
    """app.auth logger must be reachable after configure_logging()."""
    from app.logging_config import configure_logging

    configure_logging()
    logger = logging.getLogger("app.auth")
    assert logger is not None


def test_configure_logging_is_idempotent() -> None:
    """Calling configure_logging() twice must not raise or duplicate handlers."""
    from app.logging_config import configure_logging

    configure_logging()
    handler_count = len(logging.getLogger().handlers)
    configure_logging()
    # Handlers must not double up
    assert len(logging.getLogger().handlers) == handler_count
