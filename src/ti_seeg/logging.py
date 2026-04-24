"""Structured logging with per-run ID tagging."""

from __future__ import annotations

import logging
import os
import sys
import uuid
from pathlib import Path

_RUN_ID: str | None = None


def get_run_id() -> str:
    global _RUN_ID
    if _RUN_ID is None:
        _RUN_ID = os.environ.get("TI_SEEG_RUN_ID") or uuid.uuid4().hex[:8]
    return _RUN_ID


def setup_logger(
    name: str = "ti_seeg",
    level: int = logging.INFO,
    log_file: Path | None = None,
) -> logging.Logger:
    """Configure a module-level logger. Idempotent across calls."""
    logger = logging.getLogger(name)
    if getattr(logger, "_ti_seeg_configured", False):
        return logger

    logger.setLevel(level)
    run_id = get_run_id()
    fmt = logging.Formatter(
        f"%(asctime)s [{run_id}] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    logger._ti_seeg_configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ti_seeg.{name}")
