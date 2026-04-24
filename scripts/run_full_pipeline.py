#!/usr/bin/env python
"""Thin wrapper: run the entire pipeline for one subject config."""

from __future__ import annotations

import sys

from ti_seeg.cli import main

if __name__ == "__main__":
    # Default to `run` subcommand if user just passes the config.
    argv = sys.argv[1:]
    if argv and not argv[0].startswith("-") and argv[0] not in {"run", "steps", "validate"}:
        argv = ["run", "--config", argv[0], *argv[1:]]
    sys.argv = [sys.argv[0], *argv]
    main()
