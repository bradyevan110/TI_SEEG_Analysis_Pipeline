"""Tests for the efield module.

The SimNIBS-needing parts are integration-tested via the local install (when
present) by ``test_efield_integration.py``-style markers (``@pytest.mark.slow``).
The unit tests here exercise the pure-Python helpers (sampling, discovery)
that don't shell out.
"""

from __future__ import annotations

import os
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd
import pytest

from ti_seeg.source.efield import (
    find_simnibs_dir,
    sample_efield_at_contacts,
    template_m2m_dir,
)

# ---------------------------------------------------------------------------
# sample_efield_at_contacts (pure Python, no SimNIBS required)
# ---------------------------------------------------------------------------


@pytest.fixture
def envelope_nifti(tmp_path: Path) -> Path:
    """A 10x10x10 volume of constant 0.5 V/m, identity affine, saved to disk."""
    data = np.full((10, 10, 10), 0.5, dtype=np.float32)
    img = nib.Nifti1Image(data, np.eye(4))
    p = tmp_path / "envelope.nii.gz"
    nib.save(img, str(p))
    return p


def test_sample_returns_constant_for_in_volume_contacts(envelope_nifti: Path) -> None:
    electrodes = pd.DataFrame(
        {"name": ["A", "B"], "x": [4.0, 5.5], "y": [4.0, 5.5], "z": [4.0, 5.5]}
    )
    out = sample_efield_at_contacts(envelope_nifti, electrodes, radius_mm=2.0)
    assert list(out["name"]) == ["A", "B"]
    assert pytest.approx(out["envelope_mean"].iloc[0], rel=1e-6) == 0.5
    assert pytest.approx(out["envelope_max"].iloc[0], rel=1e-6) == 0.5
    assert (out["n_voxels"] > 0).all()


def test_sample_skips_invalid_coords(envelope_nifti: Path) -> None:
    electrodes = pd.DataFrame(
        {
            "name": ["good", "string_na", "nan", "out_of_volume"],
            "x": [5.0, "n/a", float("nan"), 999.0],
            "y": [5.0, 0.0, 0.0, 999.0],
            "z": [5.0, 0.0, 0.0, 999.0],
        }
    )
    out = sample_efield_at_contacts(envelope_nifti, electrodes)
    assert list(out["name"]) == ["good"]


def test_sample_no_xyz_columns_returns_empty(tmp_path: Path) -> None:
    img = nib.Nifti1Image(np.ones((4, 4, 4), dtype=np.float32), np.eye(4))
    p = tmp_path / "tiny.nii.gz"
    nib.save(img, str(p))
    electrodes = pd.DataFrame({"name": ["A"], "label": ["x"]})
    out = sample_efield_at_contacts(p, electrodes)
    assert out.empty
    assert list(out.columns) == ["name", "envelope_mean", "envelope_max", "n_voxels"]


# ---------------------------------------------------------------------------
# find_simnibs_dir / template_m2m_dir (filesystem-only)
# ---------------------------------------------------------------------------


def test_find_simnibs_dir_explicit_override(tmp_path: Path) -> None:
    fake = tmp_path / "SimNIBS-fake"
    (fake / "bin").mkdir(parents=True)
    (fake / "bin" / "charm").touch()
    (fake / "bin" / "simnibs_python").touch()
    found = find_simnibs_dir(explicit=fake)
    assert found == fake


def test_find_simnibs_dir_missing_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMNIBSDIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no_home")
    with pytest.raises(FileNotFoundError, match="Could not locate a SimNIBS install"):
        find_simnibs_dir(explicit=tmp_path / "does_not_exist")


def test_template_m2m_dir_unset_raises() -> None:
    with pytest.raises(FileNotFoundError, match="template_m2m_dir is unset"):
        template_m2m_dir(None)


def test_template_m2m_dir_existing_returns_path(tmp_path: Path) -> None:
    m2m = tmp_path / "m2m_fake"
    m2m.mkdir()
    assert template_m2m_dir(m2m) == m2m


def test_template_m2m_dir_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        template_m2m_dir(tmp_path / "does_not_exist")


# ---------------------------------------------------------------------------
# Optional integration test: requires a local SimNIBS install.
#
# Auto-detected via find_simnibs_dir(); skipped cleanly if absent.
# ---------------------------------------------------------------------------


def _simnibs_available() -> bool:
    try:
        find_simnibs_dir(explicit=os.environ.get("SIMNIBS_DIR"))
        return True
    except FileNotFoundError:
        return False


@pytest.mark.skipif(not _simnibs_available(), reason="SimNIBS not installed")
def test_simnibs_python_is_executable() -> None:
    """Sanity: the discovered simnibs_python is invokable and reports a version."""
    import subprocess

    simnibs_dir = find_simnibs_dir()
    proc = subprocess.run(
        [str(simnibs_dir / "bin" / "simnibs_python"), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Python" in proc.stdout or "Python" in proc.stderr
