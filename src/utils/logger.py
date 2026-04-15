"""
Structured logging with structlog.
JSON output for CI, pretty console output for local dev.
"""

import sys
import structlog
import logging


def setup_logging(debug: bool = False):
    """Configure structured logging for the entire application."""
    level = logging.DEBUG if debug else logging.INFO

    # Configure stdlib logging
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    # Pretty console for local, JSON for CI
    if sys.stdout.isatty():
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    """Get a named logger instance."""
    return structlog.get_logger(name)
