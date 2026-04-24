"""Smoke test for the CLI — just ensure it can validate a config."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from ti_seeg.cli import main


def _write_min_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "subj.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "subject": "001",
                "task": "tistim",
                "bids_root": str(tmp_path),
                "derivatives_root": str(tmp_path / "deriv"),
                "ti": {"f1_hz": 2000, "f2_hz": 2005, "envelope_hz": 5},
            }
        )
    )
    return cfg


def test_cli_validate_ok(tmp_path: Path) -> None:
    cfg_path = _write_min_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["validate", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert "Config OK" in result.output


def test_cli_steps_lists_all() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["steps"])
    assert result.exit_code == 0
    for s in ("preprocessing", "spectral", "tfr", "phase", "connectivity", "report"):
        assert s in result.output
