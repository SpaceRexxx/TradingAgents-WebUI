"""Centralized logging configuration.

Importing this module configures the root logger with a sensible default
format. Modules already using ``logging.getLogger(__name__)`` will
automatically pick up the format. To enable, add:

    from tradingagents.logging_config import configure_logging
    configure_logging()

at the top of an entry point (backend/main.py / cli/main.py).
"""

from __future__ import annotations

import logging
import os
import sys


_CONFIGURED = False


def configure_logging(
    level: str = None,
    *,
    log_file: str | None = None,
) -> None:
    """Initialize the root logger once. Subsequent calls are no-ops.

    Args:
        level: log level name (DEBUG / INFO / WARNING / ERROR). Defaults
            to env var ``TRADINGAGENTS_LOG_LEVEL`` or ``INFO``.
        log_file: optional path to also append logs to a file.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = level or os.environ.get("TRADINGAGENTS_LOG_LEVEL", "INFO")
    fmt = "[%(asctime)s] %(levelname)-7s %(name)-30s : %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    for h in handlers:
        h.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    root = logging.getLogger()
    root.setLevel(level.upper())
    for h in handlers:
        root.addHandler(h)

    # Silence the most verbose third-party logs unless explicitly debugging
    for noisy in ("urllib3", "httpx", "httpcore", "playwright"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger(__name__).debug("Logging configured at level=%s", level.upper())
