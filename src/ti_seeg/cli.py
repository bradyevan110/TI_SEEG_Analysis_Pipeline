"""Click-based CLI entry point: `ti-seeg ...`."""

from __future__ import annotations

import click

from .config import load_config
from .logging import setup_logger
from .pipeline import AVAILABLE_STEPS, run_pipeline


@click.group()
@click.version_option(package_name="ti-seeg")
def main() -> None:
    """TI_SEEG_Analysis_Pipeline — single-subject SEEG analysis for TI studies."""


@main.command("run")
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to subject YAML config.",
)
@click.option(
    "--steps",
    default=",".join(AVAILABLE_STEPS),
    show_default=True,
    help=f"Comma-separated subset of: {','.join(AVAILABLE_STEPS)}",
)
def run_cmd(config_path: str, steps: str) -> None:
    """Run the pipeline (or a subset of steps) for one subject."""
    setup_logger()
    cfg = load_config(config_path)
    step_list = [s.strip() for s in steps.split(",") if s.strip()]
    out_dir = run_pipeline(cfg, step_list)
    click.echo(f"Done. Outputs: {out_dir}")


@main.command("steps")
def steps_cmd() -> None:
    """List available pipeline steps."""
    for s in AVAILABLE_STEPS:
        click.echo(s)


@main.command("validate")
@click.argument("config_path", type=click.Path(exists=True, dir_okay=False))
def validate_cmd(config_path: str) -> None:
    """Parse a config and report any validation errors."""
    cfg = load_config(config_path)
    click.echo(f"Config OK: subject={cfg.subject} task={cfg.task} run={cfg.run}")
    click.echo(f"TI: f1={cfg.ti.f1_hz}, f2={cfg.ti.f2_hz}, envelope={cfg.ti.envelope_hz}")
    click.echo(f"Derivatives dir: {cfg.derivatives_dir()}")


if __name__ == "__main__":
    main()
