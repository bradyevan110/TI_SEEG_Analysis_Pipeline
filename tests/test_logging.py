"""Tests for setup_logger re-entry semantics."""

from __future__ import annotations

import logging

import pytest

from ti_seeg import logging as ti_logging


@pytest.fixture
def _reset_logger():
    """Strip ti_seeg logger config so each test starts clean."""
    logger = logging.getLogger("ti_seeg")
    for h in list(logger.handlers):
        logger.removeHandler(h)
    for attr in ("_ti_seeg_configured", "_ti_seeg_file_handler"):
        if hasattr(logger, attr):
            delattr(logger, attr)
    yield


def test_setup_logger_attaches_file_handler_after_bare_call(tmp_path, _reset_logger) -> None:
    # First call (mimics cli.py) — stdout-only.
    ti_logging.setup_logger()
    # Second call with a log_file (mimics run_pipeline) — must add a FileHandler.
    log_path = tmp_path / "pipeline.log"
    ti_logging.setup_logger(log_file=log_path)

    logger = logging.getLogger("ti_seeg")
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == str(log_path)

    logger.info("hello-from-test")
    file_handlers[0].flush()
    assert "hello-from-test" in log_path.read_text()


def test_setup_logger_does_not_double_attach_file_handler(tmp_path, _reset_logger) -> None:
    log_path = tmp_path / "pipeline.log"
    ti_logging.setup_logger(log_file=log_path)
    ti_logging.setup_logger(log_file=log_path)
    logger = logging.getLogger("ti_seeg")
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
