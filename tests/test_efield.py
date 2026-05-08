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


# ---------------------------------------------------------------------------
# Visualization (no SimNIBS required — reads the portable .npz / .nii.gz)
# ---------------------------------------------------------------------------


def test_plot_efield_orthoslice_returns_figure(envelope_nifti: Path) -> None:
    from ti_seeg.visualization.efield_plots import plot_efield_orthoslice

    fig = plot_efield_orthoslice(envelope_nifti, t1_bg=None, title="t")
    assert fig is not None
    fig.clf()


def test_plot_per_contact_envelope_handles_empty() -> None:
    from ti_seeg.visualization.efield_plots import plot_per_contact_envelope

    fig = plot_per_contact_envelope(pd.DataFrame())
    assert fig is not None
    fig.clf()


def test_plot_per_contact_envelope_with_data() -> None:
    from ti_seeg.visualization.efield_plots import plot_per_contact_envelope

    df = pd.DataFrame(
        {
            "name": ["A1", "A2", "B1"],
            "envelope_mean": [0.5, 0.3, 0.7],
            "envelope_max": [0.6, 0.4, 0.8],
            "n_voxels": [10, 10, 10],
        }
    )
    fig = plot_per_contact_envelope(df, roi_groups={"hippo": ["A1"], "amyg": ["B1"]})
    assert fig is not None
    fig.clf()


def test_plot_efield_3d_mesh_or_skip(tmp_path: Path) -> None:
    """If pyvista is installed, render a tiny synthetic mesh; otherwise skip."""
    pv = pytest.importorskip("pyvista")
    from ti_seeg.visualization.efield_plots import plot_efield_3d_mesh

    points = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )
    cells = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.int64)
    scalars = np.array([0.1, 0.5, 0.8, 0.3], dtype=np.float32)
    npz = tmp_path / "surface.npz"
    np.savez(npz, points=points, cells=cells, scalars=scalars)

    pv.OFF_SCREEN = True
    fig = plot_efield_3d_mesh(npz, contacts_df=None, title="t")
    assert fig is not None
    fig.clf()


# ---------------------------------------------------------------------------
# Slow integration: full FEM → envelope → sampling on a real m2m head model.
#
# Requires:
#   - SimNIBS install (auto-detected via find_simnibs_dir)
#   - A complete m2m_<sub>/ folder (with the .msh head mesh) supplied via
#     env var TI_SEEG_M2M_DIR. Charm itself is too slow for a smoke test.
#
# Run manually:
#   TI_SEEG_M2M_DIR=/path/to/m2m_ernie uv run pytest -m slow tests/test_efield.py
# ---------------------------------------------------------------------------


def _slow_smoke_prereqs() -> tuple[bool, str]:
    if not _simnibs_available():
        return False, "SimNIBS not installed"
    m2m_env = os.environ.get("TI_SEEG_M2M_DIR")
    if not m2m_env:
        return False, "TI_SEEG_M2M_DIR not set"
    m2m = Path(m2m_env)
    subid = m2m.name.removeprefix("m2m_")
    head_msh = m2m / f"{subid}.msh"
    if not head_msh.exists():
        return False, f"head mesh missing: {head_msh}"
    return True, ""


_SLOW_OK, _SLOW_REASON = _slow_smoke_prereqs()


@pytest.mark.slow
@pytest.mark.skipif(not _SLOW_OK, reason=_SLOW_REASON or "slow smoke prereqs not met")
def test_full_efield_pipeline_smoke(tmp_path: Path) -> None:
    """Run a single FEM solve + envelope + per-contact sampling end-to-end.

    Uses the m2m head model pointed at by $TI_SEEG_M2M_DIR. Skips if absent.
    Wall time on a modern laptop: ~5–10 minutes per FEM solve.
    """
    from ti_seeg.config import EfieldCarrierPair, EfieldElectrode
    from ti_seeg.source.efield import (
        compute_ti_envelope,
        sample_efield_at_contacts,
        simulate_carrier_pair,
    )

    simnibs_dir = find_simnibs_dir()
    m2m = Path(os.environ["TI_SEEG_M2M_DIR"])

    pair_a = EfieldCarrierPair(
        anode=EfieldElectrode(name="F3"),
        cathode=EfieldElectrode(name="P4"),
        current_mA=1.0,
        label="smoke_a",
    )
    pair_b = EfieldCarrierPair(
        anode=EfieldElectrode(name="F4"),
        cathode=EfieldElectrode(name="P3"),
        current_mA=1.0,
        label="smoke_b",
    )

    msh_a, _ = simulate_carrier_pair(m2m, pair_a, tmp_path / "pair_a", simnibs_dir=simnibs_dir)
    msh_b, _ = simulate_carrier_pair(m2m, pair_b, tmp_path / "pair_b", simnibs_dir=simnibs_dir)
    assert msh_a.exists() and msh_b.exists()

    t1_bg = m2m / "T1.nii.gz"
    msh_env, nii_env = compute_ti_envelope(
        msh_a,
        msh_b,
        out_dir=tmp_path,
        simnibs_dir=simnibs_dir,
        reference_volume=t1_bg if t1_bg.exists() else None,
    )
    assert msh_env.exists()

    if nii_env.exists():
        electrodes = pd.DataFrame({"name": ["c1"], "x": [0.0], "y": [0.0], "z": [0.0]})
        out = sample_efield_at_contacts(nii_env, electrodes, radius_mm=2.0)
        # Origin may be outside the head; the function should not crash.
        assert isinstance(out, pd.DataFrame)
