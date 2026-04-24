"""Tests for config loading + merging."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ti_seeg.config import PipelineConfig, _deep_merge, load_config


def test_deep_merge_nested() -> None:
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    override = {"a": {"y": 20, "z": 30}, "c": 4}
    merged = _deep_merge(base, override)
    assert merged == {"a": {"x": 1, "y": 20, "z": 30}, "b": 3, "c": 4}


def test_load_config_with_defaults(tmp_path: Path) -> None:
    defaults = tmp_path / "defaults.yaml"
    subject = tmp_path / "subject.yaml"

    defaults.write_text(
        yaml.safe_dump(
            {
                "preprocessing": {"line_freq": 60.0, "reference": "bipolar"},
                "tfr": {"n_freqs": 40},
            }
        )
    )
    subject.write_text(
        yaml.safe_dump(
            {
                "defaults_file": str(defaults),
                "subject": "001",
                "task": "tistim",
                "bids_root": str(tmp_path / "bids"),
                "derivatives_root": str(tmp_path / "deriv"),
                "ti": {"block_label": "excitation", "f1_hz": 2000, "f2_hz": 2005, "envelope_hz": 5},
                "tfr": {"n_freqs": 10},  # override
            }
        )
    )
    cfg = load_config(subject)
    assert isinstance(cfg, PipelineConfig)
    assert cfg.subject == "001"
    assert cfg.preprocessing.line_freq == 60.0
    assert cfg.preprocessing.reference == "bipolar"
    assert cfg.tfr.n_freqs == 10  # override beat default


def test_invalid_reference_raises(tmp_path: Path) -> None:
    subject = tmp_path / "bad.yaml"
    subject.write_text(
        yaml.safe_dump(
            {
                "subject": "001",
                "task": "tistim",
                "bids_root": str(tmp_path),
                "derivatives_root": str(tmp_path),
                "ti": {"f1_hz": 2000, "f2_hz": 2005, "envelope_hz": 5},
                "preprocessing": {"reference": "banana"},
            }
        )
    )
    with pytest.raises(Exception):
        load_config(subject)


def test_derivatives_dir(minimal_config) -> None:
    d = minimal_config.derivatives_dir()
    assert "sub-TEST" in str(d)
    assert "ses-01" in str(d)
    assert "task-synthetic" in str(d)
    assert "run-01" in str(d)
