"""TI E-field modeling via SimNIBS 4.x.

SimNIBS ships its own Python (currently 3.11) with compiled C extensions, so
we cannot ``import simnibs`` in the project's venv (Python 3.10). Instead,
SimNIBS-needing operations shell out to the bundled ``charm`` CLI and the
``simnibs_python`` interpreter via subprocess. Pure-Python work
(NIfTI sampling, plotting) stays in our venv.

Discovery of the SimNIBS install:
    1. ``efield.simnibs_dir`` config field (explicit override).
    2. ``$SIMNIBSDIR`` environment variable (its bin/ subdir or its parent).
    3. ``~/Applications/SimNIBS-*`` and ``/Applications/SimNIBS-*`` (latest).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import EfieldCarrierPair
from ..logging import get_logger

log = get_logger("source.efield")


# ---------------------------------------------------------------------------
# SimNIBS discovery
# ---------------------------------------------------------------------------


def find_simnibs_dir(explicit: str | Path | None = None) -> Path:
    """Locate the SimNIBS install root (folder containing bin/charm).

    Precedence: explicit override > $SIMNIBSDIR (or its parent) > probing
    ~/Applications/SimNIBS-* and /Applications/SimNIBS-*.
    """
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("SIMNIBSDIR")
    if env:
        env_path = Path(env)
        candidates.append(env_path)
        # $SIMNIBSDIR sometimes points at the simnibs package; walk up to find bin/.
        for parent in [env_path.parent, env_path.parent.parent, env_path.parent.parent.parent]:
            candidates.append(parent)
    for parent in [Path.home() / "Applications", Path("/Applications")]:
        if parent.is_dir():
            candidates.extend(sorted(parent.glob("SimNIBS-*"), reverse=True))

    for c in candidates:
        if (c / "bin" / "charm").exists() and (c / "bin" / "simnibs_python").exists():
            return c

    raise FileNotFoundError(
        "Could not locate a SimNIBS install. Set efield.simnibs_dir in the config "
        "(or export $SIMNIBSDIR), pointing at a folder that contains bin/charm and "
        "bin/simnibs_python. Install instructions: "
        "https://simnibs.github.io/simnibs/build/html/installation/installation.html"
    )


def _simnibs_python(simnibs_dir: Path) -> Path:
    return simnibs_dir / "bin" / "simnibs_python"


def _charm_bin(simnibs_dir: Path) -> Path:
    return simnibs_dir / "bin" / "charm"


def _run_simnibs_script(simnibs_dir: Path, script: str, *, cwd: Path | None = None) -> None:
    """Execute a Python snippet using SimNIBS's bundled interpreter."""
    cmd = [str(_simnibs_python(simnibs_dir)), "-c", script]
    log.debug("Invoking simnibs_python: %s", " ".join(cmd[:2]))
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"simnibs_python script failed (exit {proc.returncode}).\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    if proc.stdout.strip():
        log.debug("simnibs_python stdout: %s", proc.stdout.strip())


# ---------------------------------------------------------------------------
# Head model (charm)
# ---------------------------------------------------------------------------


def build_head_model(
    t1_path: str | Path,
    t2_path: str | Path | None,
    m2m_parent: Path,
    subject_id: str,
    simnibs_dir: Path,
    force: bool = False,
) -> Path:
    """Run SimNIBS ``charm`` to segment an MRI into a head mesh.

    Outputs ``m2m_<subject_id>/`` under ``m2m_parent``. Skips if a
    ``<subject_id>.msh`` already exists and ``force`` is false.
    """
    m2m_parent = Path(m2m_parent)
    m2m_parent.mkdir(parents=True, exist_ok=True)
    m2m_dir = m2m_parent / f"m2m_{subject_id}"
    head_msh = m2m_dir / f"{subject_id}.msh"
    if head_msh.exists() and not force:
        log.info("Head model exists at %s; skipping charm.", m2m_dir)
        return m2m_dir

    cmd = [str(_charm_bin(simnibs_dir)), subject_id, str(t1_path)]
    if t2_path:
        cmd.append(str(t2_path))
    if force:
        cmd.append("--forcerun")
    log.warning("Running SimNIBS charm; this typically takes 1–3 hours.")
    log.info("charm cmd: %s (cwd=%s)", " ".join(cmd), m2m_parent)
    proc = subprocess.run(cmd, cwd=str(m2m_parent))
    if proc.returncode != 0:
        raise RuntimeError(f"charm failed with exit code {proc.returncode}")
    if not head_msh.exists():
        raise RuntimeError(f"charm completed but did not produce {head_msh}")
    return m2m_dir


def template_m2m_dir(efield_template_path: str | Path | None) -> Path:
    """Return the path to a template head model for fallback use.

    SimNIBS 4.6 no longer bundles ``m2m_ernie``; users must supply a path
    via ``efield.template_m2m_dir`` (e.g., a precomputed m2m from a prior run
    or the Ernie example downloaded via SimNIBS's example scripts).
    """
    if efield_template_path is None:
        raise FileNotFoundError(
            "efield.template_m2m_dir is unset and anatomy.t1_path is null. "
            "Either set anatomy.t1_path to a subject T1, or set efield.template_m2m_dir "
            "to a precomputed m2m_<subject>/ folder. Ernie example data: "
            "https://simnibs.github.io/simnibs/build/html/dataset.html"
        )
    p = Path(efield_template_path)
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"efield.template_m2m_dir not found: {p}")
    log.warning(
        "Using template head at %s — anatomy is NOT this subject's. "
        "Per-contact predictions are normalized/approximate.",
        p,
    )
    return p


# ---------------------------------------------------------------------------
# FEM simulation per carrier pair
# ---------------------------------------------------------------------------


def _expected_sim_outputs(out_dir: Path, subid: str) -> tuple[Path, Path]:
    msh = out_dir / f"{subid}_TDCS_1_scalar.msh"
    nii = out_dir / "subject_volumes" / f"{subid}_TDCS_1_scalar_E.nii.gz"
    return msh, nii


def simulate_carrier_pair(
    m2m_dir: Path,
    pair: EfieldCarrierPair,
    out_dir: Path,
    simnibs_dir: Path,
    force: bool = False,
) -> tuple[Path, Path]:
    """Run one tDCS-style FEM simulation for a carrier pair.

    Returns ``(mesh_path, nifti_path)`` — the .msh with E-field attached and
    the volumetric NIfTI export (mapped onto the m2m T1 grid).
    """
    m2m_dir = Path(m2m_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    subid = m2m_dir.name.removeprefix("m2m_")
    expected_msh, expected_nii = _expected_sim_outputs(out_dir, subid)
    if expected_msh.exists() and expected_nii.exists() and not force:
        log.info("Simulation outputs exist at %s; skipping FEM solve.", out_dir)
        return expected_msh, expected_nii

    payload = {
        "subpath": str(m2m_dir),
        "pathfem": str(out_dir),
        "current_A": pair.current_mA * 1e-3,
        "anode": {
            "centre": pair.anode.name if pair.anode.name else pair.anode.position,
            "radius_mm": pair.anode.radius_mm,
        },
        "cathode": {
            "centre": pair.cathode.name if pair.cathode.name else pair.cathode.position,
            "radius_mm": pair.cathode.radius_mm,
        },
    }
    script = (
        "import json, sys\n"
        "from simnibs import sim_struct, run_simnibs\n"
        f"p = json.loads({json.dumps(json.dumps(payload))})\n"
        "s = sim_struct.SESSION()\n"
        "s.subpath = p['subpath']\n"
        "s.pathfem = p['pathfem']\n"
        "s.fields = 'vDeE'\n"
        "s.map_to_vol = True\n"
        "tdcs = s.add_tdcslist()\n"
        "tdcs.currents = [p['current_A'], -p['current_A']]\n"
        "tdcs.anisotropy_type = 'scalar'\n"
        "for i, key in enumerate(['anode', 'cathode']):\n"
        "    cfg = p[key]\n"
        "    el = tdcs.add_electrode()\n"
        "    el.channelnr = i + 1\n"
        "    el.centre = cfg['centre']\n"
        "    el.shape = 'ellipse'\n"
        "    el.dimensions = [cfg['radius_mm'] * 2, cfg['radius_mm'] * 2]\n"
        "    el.thickness = [4.0]\n"
        "run_simnibs(s)\n"
    )
    log.info("Running FEM solve for pair %r (current=%.2f mA)…", pair.label, pair.current_mA)
    _run_simnibs_script(simnibs_dir, script)
    if not expected_msh.exists():
        raise RuntimeError(f"FEM solve completed but {expected_msh} is missing")
    return expected_msh, expected_nii


# ---------------------------------------------------------------------------
# TI envelope (Grossman 2017 max-modulation)
# ---------------------------------------------------------------------------


def compute_ti_envelope(
    field_a_msh: Path,
    field_b_msh: Path,
    out_dir: Path,
    simnibs_dir: Path,
    reference_volume: Path | None = None,
) -> tuple[Path, Path]:
    """Combine two carrier-pair simulations into the max-modulation TI envelope.

    Uses ``simnibs.utils.TI.get_maxTI``. Writes ``ti_envelope.msh`` (mesh-
    attached field) and, if ``reference_volume`` is supplied,
    ``ti_envelope.nii.gz`` (rasterized onto the reference T1 grid).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_msh = out_dir / "ti_envelope.msh"
    out_nii = out_dir / "ti_envelope.nii.gz"

    payload = {
        "field_a": str(field_a_msh),
        "field_b": str(field_b_msh),
        "out_msh": str(out_msh),
        "out_nii": str(out_nii) if reference_volume else None,
        "reference_volume": str(reference_volume) if reference_volume else None,
    }
    script = (
        "import json\n"
        "from simnibs.utils import TI\n"
        "from simnibs import mesh_io\n"
        f"p = json.loads({json.dumps(json.dumps(payload))})\n"
        "m_a = mesh_io.read_msh(p['field_a'])\n"
        "m_b = mesh_io.read_msh(p['field_b'])\n"
        "e_a = m_a.field['E'].value\n"
        "e_b = m_b.field['E'].value\n"
        "env = TI.get_maxTI(e_a, e_b)\n"
        "m_a.add_element_field(env, 'TI_max_envelope')\n"
        "m_a.write(p['out_msh'])\n"
        "if p['out_nii']:\n"
        "    mesh_io.mesh_to_nifti(m_a, field_name='TI_max_envelope',\n"
        "        out_path=p['out_nii'], reference_volume=p['reference_volume'])\n"
    )
    log.info("Computing TI envelope from %s and %s", field_a_msh.name, field_b_msh.name)
    _run_simnibs_script(simnibs_dir, script)
    if not out_msh.exists():
        raise RuntimeError(f"compute_ti_envelope produced no mesh at {out_msh}")
    if reference_volume and not out_nii.exists():
        raise RuntimeError(f"compute_ti_envelope produced no NIfTI at {out_nii}")
    return out_msh, out_nii


# ---------------------------------------------------------------------------
# Per-contact sampling (pure Python in our venv)
# ---------------------------------------------------------------------------


def sample_efield_at_contacts(
    envelope_nifti: Path,
    electrodes: pd.DataFrame,
    radius_mm: float = 2.0,
) -> pd.DataFrame:
    """Per SEEG contact, return mean / max envelope magnitude in a sphere.

    Skips rows with NaN, ``"n/a"``, or out-of-volume coordinates with a single
    aggregated warning at the end. Returns a DataFrame with columns
    ``[name, envelope_mean, envelope_max, n_voxels]``.
    """
    import nibabel as nib

    if not {"name", "x", "y", "z"}.issubset(electrodes.columns):
        log.warning("electrodes.tsv lacks x/y/z columns; cannot sample envelope per contact.")
        return pd.DataFrame(columns=["name", "envelope_mean", "envelope_max", "n_voxels"])

    img = nib.load(str(envelope_nifti))
    data = img.get_fdata()
    inv_aff = np.linalg.inv(img.affine)
    spacing = np.array(img.header.get_zooms()[:3])
    r_vox = np.ceil(radius_mm / spacing).astype(int)

    rows: list[dict] = []
    n_skipped = 0
    for _, row in electrodes.iterrows():
        try:
            x, y, z = float(row["x"]), float(row["y"]), float(row["z"])
        except (TypeError, ValueError):
            n_skipped += 1
            continue
        if any(np.isnan([x, y, z])):
            n_skipped += 1
            continue
        vox = inv_aff @ np.array([x, y, z, 1.0])
        i, j, k = np.round(vox[:3]).astype(int)
        sub = data[
            max(0, i - int(r_vox[0])) : i + int(r_vox[0]) + 1,
            max(0, j - int(r_vox[1])) : j + int(r_vox[1]) + 1,
            max(0, k - int(r_vox[2])) : k + int(r_vox[2]) + 1,
        ]
        if sub.size == 0:
            n_skipped += 1
            continue
        rows.append(
            {
                "name": row["name"],
                "envelope_mean": float(sub.mean()),
                "envelope_max": float(sub.max()),
                "n_voxels": int(sub.size),
            }
        )

    if n_skipped:
        log.warning(
            "Skipped %d/%d contacts with missing/invalid/out-of-volume coords.",
            n_skipped,
            len(electrodes),
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Mesh → portable surface export (lets the visualization layer use pyvista
# without having to import simnibs).
# ---------------------------------------------------------------------------


def export_envelope_surface(
    envelope_msh: Path,
    out_path: Path,
    simnibs_dir: Path,
    grey_matter_tag: int = 1002,
) -> Path:
    """Extract grey-matter surface triangles + per-element envelope from a
    SimNIBS mesh and write a portable .npz (points, cells, scalars).

    This indirection keeps the SimNIBS dependency contained: downstream
    visualization can read the .npz directly with numpy/pyvista in the
    project's venv.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "msh": str(envelope_msh),
        "out": str(out_path),
        "tag": int(grey_matter_tag),
    }
    script = (
        "import json, numpy as np\n"
        "from simnibs import mesh_io\n"
        f"p = json.loads({json.dumps(json.dumps(payload))})\n"
        "m = mesh_io.read_msh(p['msh'])\n"
        "mask = m.elm.tag1 == p['tag']\n"
        "cells = m.elm.node_number_list[mask] - 1\n"
        "points = m.nodes.node_coord\n"
        "scalars = m.field['TI_max_envelope'].value[mask]\n"
        "np.savez_compressed(p['out'], points=points, cells=cells, scalars=scalars)\n"
    )
    _run_simnibs_script(simnibs_dir, script)
    if not out_path.exists():
        raise RuntimeError(f"export_envelope_surface produced no output at {out_path}")
    return out_path


__all__ = [
    "build_head_model",
    "compute_ti_envelope",
    "export_envelope_surface",
    "find_simnibs_dir",
    "sample_efield_at_contacts",
    "simulate_carrier_pair",
    "template_m2m_dir",
]
