"""Logging configuration for the shared-todos backend.

Call configure_logging() once at application startup (main.py lifespan).
All auth events are emitted on child loggers under the 'app.auth' namespace
so they can be filtered or routed independently in production.

Idempotent: repeated calls add no duplicate handlers.
"""

import logging
import sys


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)

    root.addHandler(handler)

    # Quieten noisy libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
