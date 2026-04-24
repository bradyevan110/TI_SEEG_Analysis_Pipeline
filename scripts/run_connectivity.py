#!/usr/bin/env python
"""Run spectral connectivity analysis."""

from __future__ import annotations

import click

from ti_seeg.config import load_config
from ti_seeg.logging import setup_logger
from ti_seeg.pipeline import run_pipeline


@click.command()
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
def main(config_path: str) -> None:
    setup_logger()
    cfg = load_config(config_path)
    run_pipeline(cfg, ["anatomy", "connectivity"])


if __name__ == "__main__":
    main()
