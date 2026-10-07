"""
Logging configuration for the Geospatial File Measurement API.

Configures the root logger with a structured, human-readable format.
In production, redirect to a JSON formatter or a log aggregator by
updating the ``handlers`` section.
"""
from __future__ import annotations

import logging
import logging.config


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger with a structured console formatter.

    Parameters
    ----------
    level:
        Python logging level name (``"DEBUG"``, ``"INFO"``, ``"WARNING"``,
        ``"ERROR"``, ``"CRITICAL"``). Defaults to ``"INFO"``.

    The output format is:

    ``2026-10-07 14:30:00,123 | INFO | app.services.processor | Processing completed``
    """
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {
                "level": level.upper(),
                "handlers": ["console"],
            },
            # Suppress overly verbose third-party loggers
            "loggers": {
                "uvicorn.access": {"level": "WARNING"},
                "sqlalchemy.engine": {"level": "WARNING"},
                "pyogrio": {"level": "WARNING"},
                "fiona": {"level": "WARNING"},
            },
        }
    )
