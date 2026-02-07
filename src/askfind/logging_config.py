"""Logging configuration for askfind."""

import logging
import sys
from pathlib import Path


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Configure logging for askfind.

    Args:
        verbose: Enable INFO level logging
        debug: Enable DEBUG level logging
    """
    level = logging.WARNING  # Default: only warnings and errors
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO

    # Log format
    log_format = "%(levelname)s: %(message)s"
    if debug:
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Configure root logger
    logging.basicConfig(
        level=level,
        format=log_format,
        stream=sys.stderr,  # Log to stderr, keep stdout for normal output
    )

    # Set specific logger levels
    logging.getLogger("httpx").setLevel(logging.WARNING)  # Suppress httpx debug logs
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module.

    Args:
        name: Usually __name__ from the calling module

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
