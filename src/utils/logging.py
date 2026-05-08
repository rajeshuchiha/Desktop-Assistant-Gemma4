"""Logging setup utilities."""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure basic application logging."""
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))
