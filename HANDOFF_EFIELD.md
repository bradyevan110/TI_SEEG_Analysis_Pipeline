# TI_SEEG_Analysis_Pipeline — E-Field Modeling Module (handoff)

> **Purpose of this file:** self-contained briefing for the new `efield`
> pipeline module. A fresh Claude session (or human collaborator) should be
> able to implement the module from this document alone, without needing the
> prior chat history. Read alongside the main project handoff in
> [`HANDOFF.md`](HANDOFF.md).
>
> **Last updated:** 2026-05-06
>
> **Related GitHub issues:** v2 backlog item in
> [#10](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/issues/10);
> open a fresh issue *"Implement v1 TI E-field modeling module"* and link it
> from #10's checklist before starting.

---

## 0. TL;DR

Build a new opt-in pipeline step `efield` that takes a subject's T1 (and
optional T2) MRI plus a TI scalp-stim montage, runs SimNIBS 4.x to compute
the per-carrier E-field via FEM, derives the Grossman-2017 max-modulation
TI envelope, samples the envelope at SEEG contact positions, and renders 3D
visualizations into the existing `report.html`.

- **Tool:** SimNIBS 4.x (Python API + bundled FEM solvers).
- **Install:** new optional extra group `[project.optional-dependencies] efield = […]`. Default install stays light.
- **MRI fallback:** when subject T1 is missing, simulate on SimNIBS's bundled
  `Ernie` template head with a loud warning that anatomy is normalized.
- **Caching:** segmentation (`charm`) is the slow step (~1–3 hr); cache m2m
  output under `<derivatives_root>/efield/m2m_<subject>/` and reuse on
  subsequent runs.
- **Scope:** full pipeline — segmentation + FEM solve + envelope + 3D viz +
  per-contact sampling. No optimization, no validation analyses, no
  interactive viewer (those are follow-up issues).

---

## 1. Why this matters scientifically

In a temporal-interference paradigm, two pairs of scalp electrodes carry
high-frequency carriers (e.g., 2000 Hz and 2130 Hz) whose interference
produces a low-frequency *envelope* (e.g., 130 Hz) that — in theory —
preferentially activates deep tissue at the geometric overlap of the two
fields. The envelope frequency is what we expect to entrain neurons.

For SEEG analysis this matters in two ways:

1. **Predicted hotspot localization.** A 3D E-field map tells us *where*
   the envelope is strong. For the EMOP0649 amygdala-targeted protocol,
   the envelope should peak near amygdala/hippocampus and fall off
   elsewhere. This becomes ground truth for *which* SEEG contacts ought to
   show entrainment.
2. **Artifact disambiguation.** The TI envelope appears in iEEG recordings
   directly (tissue rectification at the stim site) at the same frequency
   we want to study (130 Hz / 5 Hz). Knowing the predicted field magnitude
   per contact helps separate "this contact records the envelope passively
   because the field is strong here" from "this contact actually shows
   neural entrainment locked to the envelope" — a non-trivial distinction
   the surrogate-PLV step can't fully resolve on its own.

The Grossman 2017 envelope formula (their max-amplitude modulation across
arbitrary direction `n̂`) is the standard:

```
E_TI(r) = max over n̂ of  | |E_a(r)·n̂| − |E_b(r)·n̂| |
```

SimNIBS 4 exposes this directly via `simnibs.utils.TI.get_maxTI(field_a,
field_b)`, returning a per-element scalar on the head mesh.

---

## 2. Repository state at the time of this handoff

- Pipeline scaffold from `HANDOFF.md` v2 is in place and **all 25 unit tests
  pass** (see `git log` after commit `ac95ab1`).
- The E-field stub at
  [`src/ti_seeg/source/localization.py:102`](src/ti_seeg/source/localization.py)
  raises `NotImplementedError`. Sibling function
  `project_contact_values_to_t1` (lines 21–99) is the volume-projection
  prior art and shows the nibabel idiom we'll reuse.
- The visualization layer is matplotlib-only.
  [`src/ti_seeg/visualization/report.py`](src/ti_seeg/visualization/report.py)
  exposes `ReportBuilder.add_figure(fig: plt.Figure, …)`; pyvista renderings
  must therefore be wrapped as PNG → matplotlib `imshow` to integrate.
- [`src/ti_seeg/visualization/plots.py:100`](src/ti_seeg/visualization/plots.py)
  has `plot_contacts_on_brain` — a 2D triplet of orthogonal scatter views.
  Acceptable as a fallback when no T1 / mesh available.
- The pipeline orchestrator
  [`src/ti_seeg/pipeline/run.py`](src/ti_seeg/pipeline/run.py) defines
  `AVAILABLE_STEPS` (lines 44–54), `STEP_REGISTRY` (lines 308–318), and
  `RunContext` (lines 57–97). The closest structural analog for our new
  step is `_step_anatomy` at line 131.
- [`src/ti_seeg/config.py`](src/ti_seeg/config.py) holds the pydantic v2
  schema. `AnatomyConfig` is at lines 145–148 and currently lacks a
  `t2_path` field. `PipelineConfig` composes child configs at lines 151–179.
- [`pyproject.toml`](pyproject.toml) has `nilearn>=0.10` and `nibabel>=5.0`
  in main deps already. SimNIBS and pyvista are not yet listed.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ ti_seeg/pipeline/run.py                                          │
│  _step_efield(ctx)  ──┬──► ti_seeg/source/efield.py              │
│                       │     • build_head_model()                 │
│                       │     • mni_template_m2m_dir()             │
│                       │     • simulate_carrier_pair()            │
│                       │     • compute_ti_envelope()              │
│                       │     • sample_efield_at_contacts()        │
│                       │                                          │
│                       └──► ti_seeg/visualization/efield_plots.py │
│                             • plot_efield_orthoslice()  (nilearn)│
│                             • plot_efield_3d_mesh()    (pyvista) │
│                             • plot_per_contact_envelope() (mpl)  │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼ outputs to
                <derivatives>/efield/
                ├─ m2m_<subject>/        (cached charm output)
                ├─ pair_a/               (SimNIBS sim outputs)
                ├─ pair_b/
                ├─ ti_envelope.nii.gz    (volume)
                ├─ ti_envelope.msh       (mesh-attached)
                └─ ti_per_contact.tsv
```

Lazy import boundaries: `efield.py` imports `simnibs` and `pyvista` only
inside function bodies (or guarded by a `try/except ImportError`). This
keeps `import ti_seeg` cheap when the extra isn't installed and lets the
CLI's `validate` command keep working in lean installs.

---

## 4. Configuration schema (pydantic v2)

All new models go in [`src/ti_seeg/config.py`](src/ti_seeg/config.py). Add
imports of `tuple` types from `typing` if you need them; otherwise the
existing `BaseModel`/`Field` imports are sufficient.

```python
class EfieldElectrode(BaseModel):
    """One stim contact. Either a 10-20 name (resolved via SimNIBS's
    EEG-positions atlas) or an explicit (x, y, z) in subject MRI space."""
    name: str | None = None
    position: list[float] | None = None  # [x, y, z] in mm, MRI space
    radius_mm: float = 12.0              # SimNIBS tDCS pad default

    @field_validator("position")
    @classmethod
    def _check_position(cls, v: list[float] | None) -> list[float] | None:
        if v is not None and len(v) != 3:
            raise ValueError("position must be [x, y, z] in mm")
        return v


class EfieldCarrierPair(BaseModel):
    anode: EfieldElectrode
    cathode: EfieldElectrode
    current_mA: float = 1.0
    label: str = "carrier"


class EfieldMontage(BaseModel):
    pair_a: EfieldCarrierPair
    pair_b: EfieldCarrierPair


class EfieldConfig(BaseModel):
    enabled: bool = False
    montage: EfieldMontage | None = None
    head_model_dir: str | None = None        # explicit cache path; null = use derivatives default
    force_resegment: bool = False
    visualize_3d: bool = True
    contact_sampling_radius_mm: float = 2.0
    fallback_to_template: bool = True        # use Ernie when t1_path is null
```

Edit `AnatomyConfig` to add `t2_path`:

```python
class AnatomyConfig(BaseModel):
    t1_path: str | None = None
    t2_path: str | None = None              # NEW
    freesurfer_subjects_dir: str | None = None
    freesurfer_subject_id: str | None = None
```

Wire into `PipelineConfig` between `connectivity` and `stats`:

```python
efield: EfieldConfig = Field(default_factory=EfieldConfig)
```

---

## 5. SimNIBS integration specifics

> **Version target:** SimNIBS 4.1+ (the Python API stabilized at 4.0;
> earlier 3.x versions had a substantially different API and should not be
> supported).

### 5.1 Head segmentation (`charm`)

SimNIBS exposes `simnibs.charm.run_charm` (or the CLI `charm`). Python:

```python
from simnibs import charm
charm.run_charm(
    subid="<subject_id>",
    T1=str(t1_path),
    T2=str(t2_path) if t2_path else None,
    forceqform=True,
    forcerun=True if force else False,
)
```

`charm` writes outputs to `m2m_<subid>/` in the **current working
directory** unless overridden. Wrap with a `chdir`-context-manager (or pass
`os.chdir(parent_of_m2m)` and restore) so the m2m folder lands under
`<derivatives>/efield/`.

Expected outputs (presence check before skipping):
- `m2m_<subid>/<subid>.msh` — head mesh (tetrahedral)
- `m2m_<subid>/T1.nii.gz` — registered T1
- `m2m_<subid>/segmentation/labeling.nii.gz` — tissue segmentation
- `m2m_<subid>/eeg_positions/EEG10-10_UI_Jurak_2007.csv` — 10-20 atlas
  positions in subject space (used for resolving electrode names)

### 5.2 FEM simulation per carrier pair

SimNIBS 4 simulation API:

```python
from simnibs import sim_struct, run_simnibs

s = sim_struct.SESSION()
s.subpath = str(m2m_dir)               # m2m_<subid> directory
s.pathfem = str(out_dir)               # where SimNIBS writes the .msh + .nii.gz
s.fields = "vDeE"                       # save voltage, E vector, E magnitude

tdcs = s.add_tdcslist()
tdcs.currents = [pair.current_mA * 1e-3, -pair.current_mA * 1e-3]  # Amps
tdcs.anisotropy_type = "scalar"        # use isotropic conductivities; "vn" needs DTI

el_anode = tdcs.add_electrode()
el_anode.channelnr = 1
el_anode.centre = pair.anode.name or pair.anode.position  # str OR [x,y,z]
el_anode.shape = "ellipse"
el_anode.dimensions = [pair.anode.radius_mm * 2, pair.anode.radius_mm * 2]
el_anode.thickness = [4.0]              # mm; sponge thickness

el_cathode = tdcs.add_electrode()
el_cathode.channelnr = 2
el_cathode.centre = pair.cathode.name or pair.cathode.position
el_cathode.shape = "ellipse"
el_cathode.dimensions = [pair.cathode.radius_mm * 2, pair.cathode.radius_mm * 2]
el_cathode.thickness = [4.0]

run_simnibs(s)
```

Outputs of interest:
- `<out_dir>/<subid>_TDCS_1_scalar.msh` — mesh with E vector / magnitude attached
- `<out_dir>/subject_volumes/<subid>_TDCS_1_scalar_E.nii.gz` — volumetric E-vector NIfTI

Run once per carrier pair (so two simulations total per subject per
config). Cache the outputs and skip re-running when present.

### 5.3 TI envelope

```python
from simnibs.utils import TI
import simnibs.mesh_io as mesh_io

m_a = mesh_io.read_msh(field_a_msh)
m_b = mesh_io.read_msh(field_b_msh)

# Both meshes share a topology (same head model). Pull the E-vector field.
e_a = m_a.field["E"].value          # shape (n_elements, 3), V/m
e_b = m_b.field["E"].value

ti_envelope = TI.get_maxTI(e_a, e_b) # shape (n_elements,), V/m

# Attach back to the mesh and save.
m_out = m_a
m_out.add_element_field(ti_envelope, "TI_max_envelope")
m_out.write(out_dir / "ti_envelope.msh")

# Also export to NIfTI for nilearn-friendly visualization.
mesh_io.mesh_to_nifti(
    m_out, field_name="TI_max_envelope",
    out_path=out_dir / "ti_envelope.nii.gz",
    reference_volume=str(m2m_dir / "T1.nii.gz"),
)
```

### 5.4 Per-contact sampling

```python
import nibabel as nib
import numpy as np

img = nib.load(str(envelope_nifti))
data = img.get_fdata()
inv_aff = np.linalg.inv(img.affine)

results = []
for _, row in electrodes.iterrows():
    if pd.isna(row.x) or row.x == "n/a":
        continue
    mri_xyz = np.array([float(row.x), float(row.y), float(row.z), 1.0])
    vox_xyz = inv_aff @ mri_xyz
    i, j, k = np.round(vox_xyz[:3]).astype(int)
    # Sphere of radius_mm around (i,j,k); average the envelope inside.
    spacing = np.array(img.header.get_zooms()[:3])
    r_vox = np.ceil(radius_mm / spacing).astype(int)
    sub = data[
        max(0, i-r_vox[0]):i+r_vox[0]+1,
        max(0, j-r_vox[1]):j+r_vox[1]+1,
        max(0, k-r_vox[2]):k+r_vox[2]+1,
    ]
    results.append({"name": row["name"], "envelope_mean": float(sub.mean())})

per_contact = pd.DataFrame(results)
```

Skip rows whose `x/y/z` are NaN or the literal string `"n/a"` — emit a warning naming the count.

---

## 6. File-by-file implementation guide

### 6.1 New file: `src/ti_seeg/source/efield.py`

Approximate shape (~250 LOC):

```python
"""TI E-field modeling via SimNIBS 4.x.

All public functions lazy-import simnibs to keep the rest of the pipeline
usable without the optional `efield` extra installed.
"""

from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import os
import warnings

import numpy as np
import pandas as pd

from ..config import EfieldCarrierPair
from ..logging import get_logger

log = get_logger("source.efield")


def _require_simnibs():
    try:
        import simnibs  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "SimNIBS is required for the efield step. Install with:\n"
            "  uv sync --extra efield\n"
            "or follow https://simnibs.github.io/simnibs/build/html/installation/installation.html"
        ) from e


@contextmanager
def _chdir(path: Path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def build_head_model(
    t1_path: str | Path,
    t2_path: str | Path | None,
    m2m_parent: Path,
    subject_id: str,
    force: bool = False,
) -> Path:
    """Run SimNIBS charm. Returns path to m2m_<subject_id> directory.

    No-op if the directory already contains a complete segmentation
    (head mesh present) and `force` is False.
    """
    _require_simnibs()
    from simnibs import charm

    m2m_dir = m2m_parent / f"m2m_{subject_id}"
    head_msh = m2m_dir / f"{subject_id}.msh"
    if head_msh.exists() and not force:
        log.info("Head model exists at %s; skipping charm.", m2m_dir)
        return m2m_dir

    m2m_parent.mkdir(parents=True, exist_ok=True)
    log.warning("Running SimNIBS charm; this typically takes 1–3 hours.")
    with _chdir(m2m_parent):
        charm.run_charm(
            subid=subject_id,
            T1=str(t1_path),
            T2=str(t2_path) if t2_path else None,
            forceqform=True,
            forcerun=force,
        )
    if not head_msh.exists():
        raise RuntimeError(f"charm did not produce {head_msh}")
    return m2m_dir


def mni_template_m2m_dir() -> Path:
    """Locate the bundled Ernie m2m as a fallback when the subject has no T1."""
    _require_simnibs()
    import simnibs
    candidate = Path(simnibs.SIMNIBSDIR) / "resources" / "examples" / "ernie" / "m2m_ernie"
    if not candidate.exists():
        raise FileNotFoundError(
            f"Ernie template not found at {candidate}. "
            "Install SimNIBS examples or set efield.fallback_to_template=False."
        )
    log.warning(
        "Using Ernie template head — anatomy is NOT this subject's. "
        "Per-contact predictions are normalized/approximate."
    )
    return candidate


def simulate_carrier_pair(
    m2m_dir: Path,
    pair: EfieldCarrierPair,
    out_dir: Path,
    force: bool = False,
) -> tuple[Path, Path]:
    """Run one tDCS-style FEM simulation for a carrier pair.

    Returns (mesh_path, nifti_path) for the resulting E-field outputs.
    """
    _require_simnibs()
    from simnibs import sim_struct, run_simnibs

    out_dir.mkdir(parents=True, exist_ok=True)
    subid = m2m_dir.name.removeprefix("m2m_")
    expected_msh = out_dir / f"{subid}_TDCS_1_scalar.msh"
    expected_nii = out_dir / "subject_volumes" / f"{subid}_TDCS_1_scalar_E.nii.gz"
    if expected_msh.exists() and expected_nii.exists() and not force:
        log.info("Simulation outputs exist at %s; skipping FEM solve.", out_dir)
        return expected_msh, expected_nii

    s = sim_struct.SESSION()
    s.subpath = str(m2m_dir)
    s.pathfem = str(out_dir)
    s.fields = "vDeE"
    s.map_to_vol = True

    tdcs = s.add_tdcslist()
    tdcs.currents = [pair.current_mA * 1e-3, -pair.current_mA * 1e-3]
    tdcs.anisotropy_type = "scalar"

    for i, el_cfg in enumerate([pair.anode, pair.cathode]):
        el = tdcs.add_electrode()
        el.channelnr = i + 1
        el.centre = el_cfg.name if el_cfg.name else el_cfg.position
        el.shape = "ellipse"
        el.dimensions = [el_cfg.radius_mm * 2, el_cfg.radius_mm * 2]
        el.thickness = [4.0]

    log.info("Running FEM solve for pair %r (current=%.1f mA)…", pair.label, pair.current_mA)
    run_simnibs(s)
    return expected_msh, expected_nii


def compute_ti_envelope(
    field_a_msh: Path,
    field_b_msh: Path,
    out_dir: Path,
    reference_volume: Path | None = None,
) -> tuple[Path, Path]:
    """Combine two carrier-pair simulations into the Grossman 2017 max-modulation
    TI envelope. Returns (envelope_msh, envelope_nifti) paths."""
    _require_simnibs()
    from simnibs.utils import TI
    import simnibs.mesh_io as mesh_io

    m_a = mesh_io.read_msh(str(field_a_msh))
    m_b = mesh_io.read_msh(str(field_b_msh))

    e_a = m_a.field["E"].value
    e_b = m_b.field["E"].value
    envelope = TI.get_maxTI(e_a, e_b)

    out_msh = out_dir / "ti_envelope.msh"
    out_nii = out_dir / "ti_envelope.nii.gz"

    m_a.add_element_field(envelope, "TI_max_envelope")
    m_a.write(str(out_msh))

    if reference_volume:
        mesh_io.mesh_to_nifti(
            m_a,
            field_name="TI_max_envelope",
            out_path=str(out_nii),
            reference_volume=str(reference_volume),
        )
    return out_msh, out_nii


def sample_efield_at_contacts(
    envelope_nifti: Path,
    electrodes: pd.DataFrame,
    radius_mm: float = 2.0,
) -> pd.DataFrame:
    """Per SEEG contact, return mean envelope amplitude in a sphere of radius_mm.

    Skips rows with NaN / 'n/a' coordinates. Returns DataFrame with columns
    [name, envelope_mean, envelope_max, n_voxels].
    """
    import nibabel as nib

    if not {"name", "x", "y", "z"}.issubset(electrodes.columns):
        log.warning("electrodes.tsv lacks x/y/z; cannot sample envelope per contact.")
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
            max(0, i - r_vox[0]):i + r_vox[0] + 1,
            max(0, j - r_vox[1]):j + r_vox[1] + 1,
            max(0, k - r_vox[2]):k + r_vox[2] + 1,
        ]
        if sub.size == 0:
            n_skipped += 1
            continue
        rows.append({
            "name": row["name"],
            "envelope_mean": float(sub.mean()),
            "envelope_max": float(sub.max()),
            "n_voxels": int(sub.size),
        })

    if n_skipped:
        log.warning("Skipped %d/%d contacts with missing/invalid coords.", n_skipped, len(electrodes))

    return pd.DataFrame(rows)
```

### 6.2 New file: `src/ti_seeg/visualization/efield_plots.py`

```python
"""3D visualization helpers for TI E-field outputs."""

from __future__ import annotations
from pathlib import Path
import tempfile

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..logging import get_logger

log = get_logger("visualization.efield_plots")


def plot_efield_orthoslice(
    envelope_nifti: Path,
    t1_bg: Path | None = None,
    threshold: float | None = None,
    title: str = "TI envelope",
) -> plt.Figure:
    """Three orthogonal slices through the envelope volume, optionally
    overlaid on the subject T1. Uses nilearn (already a main dep)."""
    from nilearn import plotting

    fig = plt.figure(figsize=(12, 4))
    plotting.plot_stat_map(
        str(envelope_nifti),
        bg_img=str(t1_bg) if t1_bg else None,
        threshold=threshold,
        title=title,
        figure=fig,
        display_mode="ortho",
        cmap="hot",
        colorbar=True,
    )
    return fig


def plot_efield_3d_mesh(
    envelope_msh: Path,
    contacts_df: pd.DataFrame | None = None,
    title: str = "TI envelope (3D)",
) -> plt.Figure:
    """Off-screen pyvista render of the head mesh colormapped by envelope
    magnitude, with SEEG contacts as spheres. Returns a matplotlib Figure
    wrapping the screenshot so the existing ReportBuilder can embed it."""
    try:
        import pyvista as pv
    except ImportError as e:
        raise ImportError(
            "pyvista is required for 3D E-field plots. Install with `uv sync --extra efield`."
        ) from e
    import simnibs.mesh_io as mesh_io

    pv.OFF_SCREEN = True
    pv.global_theme.window_size = [1024, 768]

    m = mesh_io.read_msh(str(envelope_msh))
    # Convert SimNIBS mesh to pyvista UnstructuredGrid (helper in simnibs;
    # if not available, build manually from m.elm.node_number_list and m.nodes.node_coord).
    points = m.nodes.node_coord
    cells = m.elm.node_number_list - 1  # SimNIBS is 1-indexed
    # Filter to surface elements (gray matter / cortex). Tag depends on SimNIBS version;
    # commonly 1002 = grey matter surface. Confirm against the loaded mesh.
    grey_mask = m.elm.tag1 == 1002
    grey_cells = cells[grey_mask]

    cells_pv = np.hstack([
        np.full((grey_cells.shape[0], 1), grey_cells.shape[1]),
        grey_cells,
    ]).astype(np.int64)
    grid = pv.UnstructuredGrid(cells_pv, np.full(grey_cells.shape[0], pv.CellType.TRIANGLE), points)
    envelope = m.field["TI_max_envelope"].value[grey_mask]
    grid["TI"] = envelope

    plotter = pv.Plotter(off_screen=True)
    plotter.add_mesh(grid, scalars="TI", cmap="hot", opacity=0.9, smooth_shading=True)

    if contacts_df is not None and {"x", "y", "z"}.issubset(contacts_df.columns):
        valid = contacts_df.dropna(subset=["x", "y", "z"])
        for _, c in valid.iterrows():
            plotter.add_mesh(
                pv.Sphere(radius=2.0, center=(c.x, c.y, c.z)),
                color="cyan",
                render_points_as_spheres=True,
            )

    plotter.add_text(title, font_size=12)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        png_path = Path(f.name)
    plotter.screenshot(str(png_path), window_size=[1024, 768])
    plotter.close()

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.imshow(plt.imread(png_path))
    ax.axis("off")
    fig.tight_layout()
    png_path.unlink(missing_ok=True)
    return fig


def plot_per_contact_envelope(
    per_contact: pd.DataFrame,
    roi_groups: dict[str, list[str]] | None = None,
    title: str = "Predicted TI envelope per contact",
) -> plt.Figure:
    """Bar chart of envelope_mean per contact, color-coded by ROI."""
    df = per_contact.copy().sort_values("envelope_mean", ascending=False)
    color_lookup = {}
    if roi_groups:
        palette = plt.cm.tab20(np.linspace(0, 1, max(1, len(roi_groups))))
        for (roi, chans), col in zip(roi_groups.items(), palette, strict=False):
            for ch in chans:
                color_lookup[ch] = col

    colors = [color_lookup.get(n, "#888888") for n in df["name"]]
    fig, ax = plt.subplots(figsize=(max(8, len(df) * 0.05), 4))
    ax.bar(df["name"], df["envelope_mean"], color=colors)
    ax.set_xticklabels(df["name"], rotation=90, fontsize=5)
    ax.set_ylabel("E-field magnitude (V/m)")
    ax.set_title(title)
    fig.tight_layout()
    return fig
```

### 6.3 New file: `tests/test_efield.py`

```python
"""Tests for the efield module. All gated on simnibs availability."""

from __future__ import annotations
import numpy as np
import pandas as pd
import pytest

simnibs = pytest.importorskip("simnibs")
from ti_seeg.source.efield import (
    compute_ti_envelope,
    sample_efield_at_contacts,
)


def test_get_maxTI_orthogonal_unit_fields():
    """If E_a and E_b are orthogonal unit vectors at every element, the TI
    envelope should be 0 everywhere (Grossman 2017)."""
    from simnibs.utils import TI
    n = 100
    e_a = np.tile([1.0, 0.0, 0.0], (n, 1))
    e_b = np.tile([0.0, 1.0, 0.0], (n, 1))
    env = TI.get_maxTI(e_a, e_b)
    assert np.allclose(env, 0.0, atol=1e-6)


def test_get_maxTI_parallel_fields_equal_magnitudes():
    """Identical parallel fields → envelope = 0 (no modulation possible)."""
    from simnibs.utils import TI
    n = 100
    e = np.tile([2.0, 0.0, 0.0], (n, 1))
    env = TI.get_maxTI(e.copy(), e.copy())
    assert np.allclose(env, 0.0, atol=1e-6)


def test_get_maxTI_antiparallel_fields():
    """Anti-parallel fields → envelope = 2 * magnitude (Grossman 2017)."""
    from simnibs.utils import TI
    n = 50
    e_a = np.tile([1.0, 0.0, 0.0], (n, 1))
    e_b = np.tile([-1.0, 0.0, 0.0], (n, 1))
    env = TI.get_maxTI(e_a, e_b)
    assert np.allclose(env, 2.0, atol=1e-6)


def test_sample_efield_at_contacts_skips_invalid_coords(tmp_path):
    """Rows with NaN / 'n/a' coords should be silently skipped."""
    import nibabel as nib
    data = np.ones((10, 10, 10), dtype=np.float32) * 0.5
    img = nib.Nifti1Image(data, np.eye(4))
    nii_path = tmp_path / "envelope.nii.gz"
    nib.save(img, str(nii_path))

    electrodes = pd.DataFrame({
        "name": ["A", "B", "C"],
        "x": [5.0, "n/a", float("nan")],
        "y": [5.0, 0, 0],
        "z": [5.0, 0, 0],
    })
    out = sample_efield_at_contacts(nii_path, electrodes)
    assert len(out) == 1
    assert out["name"].iloc[0] == "A"
    assert pytest.approx(out["envelope_mean"].iloc[0], rel=1e-3) == 0.5


@pytest.mark.slow
def test_simulate_smoke_on_ernie(tmp_path):
    """Smoke test the full simulate pipeline on Ernie. Slow; mark accordingly."""
    from ti_seeg.source.efield import (
        mni_template_m2m_dir, simulate_carrier_pair,
    )
    from ti_seeg.config import EfieldCarrierPair, EfieldElectrode

    m2m = mni_template_m2m_dir()
    pair = EfieldCarrierPair(
        anode=EfieldElectrode(name="F3"),
        cathode=EfieldElectrode(name="P4"),
        current_mA=1.0,
        label="smoke",
    )
    msh, nii = simulate_carrier_pair(m2m, pair, tmp_path / "sim_smoke")
    assert msh.exists()
    assert nii.exists()
```

Add `slow` to `[tool.pytest.ini_options] markers` in `pyproject.toml`:

```toml
markers = ["slow: long-running tests (FEM solve, segmentation)"]
```

### 6.4 Modify: `src/ti_seeg/source/__init__.py`

```python
"""Anatomical mapping + TI E-field modeling."""

from .efield import (
    build_head_model,
    compute_ti_envelope,
    mni_template_m2m_dir,
    sample_efield_at_contacts,
    simulate_carrier_pair,
)
from .localization import project_contact_values_to_t1

__all__ = [
    "build_head_model",
    "compute_ti_envelope",
    "mni_template_m2m_dir",
    "project_contact_values_to_t1",
    "sample_efield_at_contacts",
    "simulate_carrier_pair",
]
```

Remove `compute_ti_field` from exports and from
`source/localization.py` entirely (the stub is superseded).

### 6.5 Modify: `src/ti_seeg/visualization/__init__.py`

Add the new exports (`plot_efield_orthoslice`, `plot_efield_3d_mesh`, `plot_per_contact_envelope`).

### 6.6 Modify: `src/ti_seeg/pipeline/run.py`

Append `"efield"` to `AVAILABLE_STEPS` (right after `"anatomy"`):

```python
AVAILABLE_STEPS = [
    "preprocessing",
    "anatomy",
    "efield",          # NEW
    "spectral",
    "tfr",
    "phase",
    "cfc",
    "connectivity",
    "stats",
    "report",
]
```

Add the step function (mirror `_step_anatomy` shape):

```python
def _step_efield(ctx: RunContext) -> None:
    cfg = ctx.config.efield
    if not cfg.enabled:
        log.info("efield.enabled=false; skipping E-field step.")
        return
    if cfg.montage is None:
        raise ValueError("efield.enabled is true but efield.montage is unset.")

    from ..source.efield import (
        build_head_model, mni_template_m2m_dir,
        simulate_carrier_pair, compute_ti_envelope, sample_efield_at_contacts,
    )
    from ..visualization.efield_plots import (
        plot_efield_orthoslice, plot_efield_3d_mesh, plot_per_contact_envelope,
    )

    bids = ctx.load_bids()
    efield_dir = ensure_dir(ctx.out_dir / "efield")

    # Resolve head model.
    if ctx.config.anatomy.t1_path:
        m2m_parent = (
            Path(cfg.head_model_dir) if cfg.head_model_dir
            else efield_dir
        )
        m2m = build_head_model(
            t1_path=ctx.config.anatomy.t1_path,
            t2_path=ctx.config.anatomy.t2_path,
            m2m_parent=m2m_parent,
            subject_id=ctx.config.subject,
            force=cfg.force_resegment,
        )
        t1_bg = m2m / "T1.nii.gz"
    elif cfg.fallback_to_template:
        log.warning(
            "anatomy.t1_path is null; using bundled template head — predictions are approximate."
        )
        m2m = mni_template_m2m_dir()
        t1_bg = m2m / "T1.nii.gz"
    else:
        raise ValueError(
            "anatomy.t1_path is null and efield.fallback_to_template is false; "
            "cannot run efield step."
        )

    # Run per-pair FEM solves.
    pair_dirs = {}
    for label, pair in [("a", cfg.montage.pair_a), ("b", cfg.montage.pair_b)]:
        out = efield_dir / f"pair_{label}"
        msh, nii = simulate_carrier_pair(m2m, pair, out, force=cfg.force_resegment)
        pair_dirs[label] = (msh, nii)

    # TI envelope.
    msh_env, nii_env = compute_ti_envelope(
        pair_dirs["a"][0], pair_dirs["b"][0],
        out_dir=efield_dir,
        reference_volume=t1_bg,
    )

    # Per-contact sampling.
    per_contact = sample_efield_at_contacts(
        nii_env, bids.electrodes, radius_mm=cfg.contact_sampling_radius_mm,
    )
    per_contact.to_csv(efield_dir / "ti_per_contact.tsv", sep="\t", index=False)

    # Visualizations.
    fig_ortho = plot_efield_orthoslice(nii_env, t1_bg=t1_bg, title="TI envelope")
    ctx.report.add_figure(fig_ortho, title="TI envelope (orthogonal)", section="efield")

    if cfg.visualize_3d:
        fig_3d = plot_efield_3d_mesh(msh_env, contacts_df=bids.electrodes)
        ctx.report.add_figure(fig_3d, title="TI envelope (3D)", section="efield")

    fig_bar = plot_per_contact_envelope(per_contact, ctx.roi_groups)
    ctx.report.add_figure(fig_bar, title="Predicted envelope per contact", section="efield")

    log.info("efield step done. Per-contact rows: %d", len(per_contact))
```

Register in `STEP_REGISTRY`:

```python
STEP_REGISTRY = {
    "preprocessing": _step_preprocessing,
    "anatomy": _step_anatomy,
    "efield": _step_efield,    # NEW
    "spectral": _step_spectral,
    ...
}
```

### 6.7 Modify: `pyproject.toml`

Add to `[project.optional-dependencies]`:

```toml
efield = [
    "simnibs>=4.1",
    "pyvista>=0.43",
]
```

Add to `[tool.pytest.ini_options]`:

```toml
markers = ["slow: long-running tests (FEM solve, segmentation)"]
```

Run `--exclude slow` by default? Up to you. SimNIBS-bundled smoke tests
take 1–10 minutes; that's tolerable to run on demand but probably should
be excluded from the default `pytest` invocation in CI.

### 6.8 Modify: `configs/analysis_defaults.yaml`

Add at the bottom:

```yaml
efield:
  enabled: false                    # opt-in; expensive
  montage: null                     # subject configs must populate
  head_model_dir: null              # null -> derivatives_root/efield/
  force_resegment: false
  visualize_3d: true
  contact_sampling_radius_mm: 2.0
  fallback_to_template: true
```

### 6.9 Modify: `configs/subject_template.yaml`

Append a commented example:

```yaml
# Example efield block — enable + populate before running with --steps efield.
# Carrier pairs deliver high-frequency stim; the envelope = |f1 - f2|.
# efield:
#   enabled: true
#   montage:
#     pair_a:
#       anode: { name: "F4", radius_mm: 12.0 }
#       cathode: { name: "P4", radius_mm: 12.0 }
#       current_mA: 1.0
#       label: "carrier_2000Hz"
#     pair_b:
#       anode: { name: "F8", radius_mm: 12.0 }
#       cathode: { name: "P8", radius_mm: 12.0 }
#       current_mA: 1.0
#       label: "carrier_2130Hz"
#   visualize_3d: true
#   contact_sampling_radius_mm: 2.0
```

### 6.10 Modify: `HANDOFF.md` and `configs/subject_EMOP0649_run0X.yaml`

Update the §6 outstanding-work bullet about E-field to reflect that this
module is being implemented (or remove and link to the new GitHub issue).

For EMOP0649 specifically, when MRI lands in the BIDS folder, the user
will set:

```yaml
anatomy:
  t1_path: /Users/ebrady/Projects/SEEG Processing/sub-EMOP0649/anat/sub-EMOP0649_T1w.nii.gz
  t2_path: /Users/ebrady/Projects/SEEG Processing/sub-EMOP0649/anat/sub-EMOP0649_T2w.nii.gz

efield:
  enabled: true
  montage:
    pair_a:
      anode: { name: "<TBD>", radius_mm: 12.0 }
      cathode: { name: "<TBD>", radius_mm: 12.0 }
      current_mA: 1.0
      label: "carrier_2000Hz"
    pair_b:
      anode: { name: "<TBD>", radius_mm: 12.0 }
      cathode: { name: "<TBD>", radius_mm: 12.0 }
      current_mA: 1.0
      label: "carrier_2130Hz"
```

The `<TBD>` placeholders are filled from the user's stim protocol notes.

---

## 7. Implementation order (recommended)

Land changes in small, independently mergeable commits:

1. **Schema + extra dep group.** `pyproject.toml` + `config.py` + `analysis_defaults.yaml`. Run `uv sync` (no `--extra efield`) and `uv run pytest` to confirm 25/25 still green and the schema parses.
2. **Stub the new step.** Add `_step_efield` registered but raising `NotImplementedError` if called; add `"efield"` to `AVAILABLE_STEPS`. CLI's `validate` now accepts efield blocks; `run --steps efield` raises clearly.
3. **Implement `efield.py` core functions.** Stubs first: `build_head_model`, `mni_template_m2m_dir`, `simulate_carrier_pair`, `compute_ti_envelope`, `sample_efield_at_contacts`. Add `tests/test_efield.py` with the synthetic `get_maxTI` and `sample_efield_at_contacts` tests (don't run the slow Ernie smoke yet).
4. **Wire `_step_efield` to call them.** End-to-end on Ernie + a fake `electrodes.tsv` with NaN coords; verify the step produces `ti_envelope.nii.gz` and writes a (empty) `ti_per_contact.tsv`.
5. **Visualization.** `efield_plots.py` + integration in `_step_efield`. Verify `report.html` opens with all three new figures.
6. **Slow smoke test.** Mark `test_simulate_smoke_on_ernie` `@pytest.mark.slow`; run manually `uv run pytest -m slow`.
7. **Real-MRI dry run.** When EMOP0649's T1/T2 land, configure `anatomy.t1_path` and run `--steps anatomy,efield,report`. First run: ~1–3 hr. Inspect report.

Open one GitHub issue per landing step (stack them with checkboxes in a tracking issue) so progress is visible on the repo.

---

## 8. Verification / acceptance criteria

The module is "done" for v1 when **all** of these hold:

1. `uv sync` (no extra) succeeds; `uv run pytest` reports 25 + new
   `test_efield.py` non-slow tests passing; SimNIBS-gated tests skip
   cleanly with a printed reason.
2. `uv sync --extra efield` succeeds; `uv run pytest -m slow` runs the
   Ernie smoke test (~5–10 min) and passes.
3. `uv run ti-seeg validate configs/subject_EMOP0649_run01.yaml` succeeds
   both with `efield.enabled: false` and with a populated montage block.
4. `uv run ti-seeg run --config <subj-with-no-T1>.yaml --steps anatomy,efield,report`
   uses the Ernie fallback and produces:
   - `<derivatives>/efield/ti_envelope.nii.gz`
   - `<derivatives>/efield/ti_envelope.msh`
   - `<derivatives>/efield/ti_per_contact.tsv` (may be empty if all coords are `n/a`)
   - `<derivatives>/figures/efield_*.png` × 3
   - A clear warning in the log: `Using Ernie template head — anatomy is NOT this subject's. Per-contact predictions are normalized/approximate.`
5. With a real T1+T2 (subject in BIDS), the same command yields a report
   where the envelope hotspot is visibly near the stim target (e.g.,
   amygdala for EMOP0649) and the per-contact bar chart ranks
   target-shank contacts at the top.
6. Re-running the pipeline reads the cached m2m and per-pair sims; total
   wall time drops from hours to minutes.
7. Disabling the extra (`uv sync` without `--extra efield`) and running
   `--steps efield` raises a clean `ImportError` pointing at the install
   command — *not* a confusing tracebacks deep inside SimNIBS.

---

## 9. Known gotchas

1. **SimNIBS `charm` writes outputs in the CWD.** Always wrap calls in
   the `_chdir` context manager pointing at the desired parent directory.
2. **Mesh tags are version-dependent.** Grey-matter element tag is `1002`
   in SimNIBS 4 but verify against the loaded mesh
   (`np.unique(m.elm.tag1)`) before hard-coding. Wrong tag → empty mesh
   in the 3D plot.
3. **Coordinate frames must match.** SimNIBS works in subject MRI/scanner
   space (RAS). When the user adds SEEG coordinates from external software
   (FreeSurfer, BrainSight, Leksell), confirm they're in the same frame
   as the T1 used by `charm`. If they're in CT space or atlas space,
   apply a transform before sampling.
4. **`SimNIBSDIR` is set on simnibs install.** `simnibs.SIMNIBSDIR` points
   at the install root. The bundled Ernie may live in
   `resources/examples/ernie/m2m_ernie/` (4.1) or
   `examples/ernie/m2m_ernie/` (older 4.x). Probe both and bail with a
   helpful error if neither exists.
5. **Off-screen pyvista on macOS.** Works via VTK's `vtkOSPRayPass` /
   `vtkOpenGLRenderWindow`. If the Plotter hangs, set `pv.OFF_SCREEN =
   True` *before* importing any other VTK-backed module and verify
   `os.environ.get("DISPLAY")` is unset / set appropriately. On
   headless Linux you may need `xvfb-run`.
6. **Large meshes are slow to render.** Filter to grey-matter surface
   before sending to pyvista (the example code does this with
   `tag1 == 1002`). Otherwise the screenshot can take >30 s and produce
   an unreadable interior view.
7. **`mesh_to_nifti` resolution.** SimNIBS rasterizes the mesh field onto
   the reference volume's voxel grid. Default is the reference T1 resolution
   (typically 1 mm isotropic), which is fine; if the reference is
   anisotropic the per-contact sampling needs to use voxel spacing
   correctly (the code in §5.4 does).
8. **Stim-electrode placement for TI is non-trivial.** The user must
   supply real stim sites — these are typically *different* electrodes
   from the recording montage. The 19 EEG channels in EMOP0649's
   `channels.tsv` are recording electrodes, not the TI stim sites.
9. **Bilateral montages.** Some TI protocols use 4 stim electrodes
   (2 carriers × 2 electrodes each) where the two pairs straddle the
   target. Other protocols use shared cathodes etc. The current schema
   supports the canonical 2-pair-of-2 layout; if the protocol differs,
   extend `EfieldMontage` rather than working around the schema.
10. **DWI is in BIDS but unused.** SimNIBS supports DTI-derived
    anisotropic conductivities (`tdcs.anisotropy_type = "vn"`) which
    can subtly improve fields in white matter. Out of scope for v1; open
    a follow-up issue if fidelity demands it.

---

## 10. Out of scope (follow-up issues)

- **Validation analysis:** systematic comparison of predicted envelope
  against measured PLV-to-envelope across contacts. This is a separate
  scientific question and warrants its own notebook.
- **Interactive 3D viewer in the report:** `pyvista.Plotter.export_html`
  produces a self-contained HTML widget; embedding it in `mne.Report` is
  tractable but adds JS asset management overhead. Defer.
- **Multi-pair / multi-frequency optimization:** searching the montage
  space to maximize predicted target field. This is a research project,
  not pipeline plumbing.
- **DTI-anisotropic conductivities:** the user has DWI but the standard
  charm path uses isotropic. Switching adds 1–2 hours of preprocessing per
  subject (DTI prep + tensor estimation).
- **Hippocampal subfield atlas (ASHS):** finer-grained ROI coupling than
  shank-prefix. Tracked in `HANDOFF.md` v2 backlog.

---

## 11. References

- Grossman et al. (2017). "Noninvasive Deep Brain Stimulation via
  Temporally Interfering Electric Fields." *Cell* 169(6):1029–1041.
- Saturnino et al. (2019). "SimNIBS 2.1: A Comprehensive Pipeline for
  Individualized Electric Field Modelling for Transcranial Brain
  Stimulation." *Brain and Human Body Modeling*, Springer.
- SimNIBS 4 documentation: <https://simnibs.github.io/simnibs/>
- SimNIBS TI utilities API:
  `simnibs.utils.TI.get_maxTI`, `simnibs.utils.TI.get_dirTI`.
- pyvista off-screen rendering:
  <https://docs.pyvista.org/version/stable/user-guide/jupyter/>
- nilearn `plot_stat_map`:
  <https://nilearn.github.io/stable/modules/generated/nilearn.plotting.plot_stat_map.html>

---

## 12. First prompt for the implementing session

> "Picking up the TI E-field module on TI_SEEG_Analysis_Pipeline. Read
> `HANDOFF.md` (project state) and `HANDOFF_EFIELD.md` (this module's plan)
> at the repo root. Implement the module in the order listed in §7 of
> HANDOFF_EFIELD.md, opening one PR per step. Land §7.1 (schema +
> extra dep group + stub step) first; ping me before starting §7.3
> (the heavy SimNIBS wrapper). Do not run any FEM solves on the dev
> machine without confirming RAM/disk headroom — the segmentation alone
> writes ~2 GB per subject."
