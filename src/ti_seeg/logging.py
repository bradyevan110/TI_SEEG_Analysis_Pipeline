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
    """Configure a module-level logger.

    Safe to call multiple times: the stream handler is added once, and a file
    handler is attached the first time `log_file` is supplied (so the typical
    flow — bare `setup_logger()` in the CLI, then `setup_logger(log_file=...)`
    once the derivatives dir is known — both works and persists logs to disk).
    """
    logger = logging.getLogger(name)
    run_id = get_run_id()
    fmt = logging.Formatter(
        f"%(asctime)s [{run_id}] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not getattr(logger, "_ti_seeg_configured", False):
        logger.setLevel(level)
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(fmt)
        logger.addHandler(stream)
        logger._ti_seeg_configured = True  # type: ignore[attr-defined]

    if log_file is not None and not getattr(logger, "_ti_seeg_file_handler", False):
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
        logger._ti_seeg_file_handler = True  # type: ignore[attr-defined]

    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ti_seeg.{name}")
