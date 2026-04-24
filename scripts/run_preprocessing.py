#!/usr/bin/env python
"""Run only the preprocessing step."""

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
    out = run_pipeline(cfg, ["preprocessing"])
    click.echo(f"Preprocessed raw at: {out / 'preprocessed_raw.fif'}")


if __name__ == "__main__":
    main()
