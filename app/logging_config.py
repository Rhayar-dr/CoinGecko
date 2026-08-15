"""Centralised logging configuration.

Produces log lines like::

    2026-08-15 03:00:01 INFO Starting bitcoin extraction

Call :func:`configure_logging` once at process start (the CLI does this).
Everywhere else use ``logging.getLogger(__name__)``.
"""

from __future__ import annotations

import logging

_LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger. Idempotent — safe to call more than once."""
    global _configured
    if _configured:
        logging.getLogger().setLevel(level)
        return

    logging.basicConfig(level=level, format=_LOG_FORMAT, datefmt=_DATE_FORMAT)
    # Quiet down noisy third-party loggers.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    _configured = True
