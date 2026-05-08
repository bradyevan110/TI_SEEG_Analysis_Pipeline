# TI_SEEG_Analysis_Pipeline — E-Field Modeling Module (post-implementation handoff)

> **Purpose of this file:** self-contained briefing for the next Claude
> session (or human collaborator) who picks up the `efield` pipeline
> module. Reflects what has actually been implemented in PRs #12–#17,
> not the original design plan. Read alongside the main project handoff
> in [`HANDOFF.md`](HANDOFF.md).
>
> **Last updated:** 2026-05-08 (after PRs #12–#17 stacked against `main`)
>
> **Tracking issue:**
> [#11](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/issues/11)

---

## 0. Status at a glance

| Step | PR | State | What landed |
|---|---|---|---|
| 7.1 | [#12](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/12) | open / awaiting review | `EfieldConfig` family + `t2_path` + `efield` extra + YAML defaults + `slow` marker |
| 7.2 | [#13](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/13) | open, stacked on #12 | `_step_efield` registered with `NotImplementedError` |
| 7.3 | [#14](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/14) | open, stacked on #13 | `src/ti_seeg/source/efield.py` core wrapper (subprocess) + 9 unit tests |
| 7.4 | [#15](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/15) | open, stacked on #14 | `_step_efield` wired to call charm + FEM + envelope + sampling |
| 7.5 | [#16](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/16) | open, stacked on #15 | `efield_plots.py` (orthoslice + 3D pyvista + per-contact bar) + report integration |
| 7.6 | [#17](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/17) | open, stacked on #16 | `@pytest.mark.slow` end-to-end smoke gated on `$TI_SEEG_M2M_DIR` |
| 7.7 | — | TODO | Real-MRI dry run on EMOP0649 (§9 of this doc) |

PRs are **stacked**: #13 targets #12, #14 targets #13, etc. Merge in
order, or squash-merge each as #12 lands and let the others rebase onto
`main`. Each PR is self-contained but assumes its predecessors.

Test count on the top branch: **39 collected, 38 pass, 1 skip** (pyvista
not installed in the project venv; skipped cleanly).

`efield.enabled=false` is the default; the rest of the pipeline runs
unchanged for users who don't opt in.

---

## 1. Local environment

This module was developed against a specific local SimNIBS install on the
maintainer's machine. The discovery code falls back to standard locations
elsewhere.

- **SimNIBS install:** `/Users/ebrady/Applications/SimNIBS-4.6/`
  - CLI binaries: `bin/{charm,simnibs,simnibs_python,simnibs_gui,…}`
  - Bundled Python: `simnibs_env/bin/python` → Python **3.11.14**
  - `simnibs.SIMNIBSDIR` resolves to `simnibs_env/lib/python3.11/site-packages/simnibs`
- **Project venv:** Python **3.10.0** at `.venv/` (managed by `uv`).
- **Why two Pythons:** SimNIBS 4.6 ships its own conda env with compiled
  C extensions tied to its bundled deps. Mixing them via PYTHONPATH or
  `pip install simnibs` into our venv is unsupported, and SimNIBS isn't
  on PyPI in any case. The module **shells out** instead.
- **Precomputed reference m2m heads** (the maintainer's TI-Toolbox repo):
  - `/Users/ebrady/Projects/TI_Toolbox/code/ti-toolbox/TI-Toolbox/derivatives/SimNIBS/sub-ernie/m2m_ernie/`
    *(incomplete — only T1 + settings.ini; charm did not finish)*
  - `…/sub-MNI152/m2m_MNI152/`
  - `…/sub-ernie/anat/sub-ernie_T1w.nii` is a usable T1 for running charm.

---

## 2. Architecture as built (deviates from original plan)

```
┌──────────────────────────────────────────────────────────────────┐
│  ti_seeg.pipeline.run._step_efield  (in our venv, Python 3.10)   │
│        │                                                          │
│        ├── ti_seeg.source.efield                                 │
│        │     find_simnibs_dir   ─┐                                │
│        │     build_head_model    │  subprocess(`charm` CLI)       │
│        │     simulate_carrier_pair─┐                              │
│        │     compute_ti_envelope ─┼──► subprocess                 │
│        │     export_envelope_surface─┘   (`simnibs_python -c`)    │
│        │                                                          │
│        │     sample_efield_at_contacts  (pure-numpy + nibabel)    │
│        │     template_m2m_dir            (filesystem checks)      │
│        │                                                          │
│        └── ti_seeg.visualization.efield_plots                     │
│              plot_efield_orthoslice     (nilearn, no SimNIBS)     │
│              plot_efield_3d_mesh        (pyvista, reads .npz)     │
│              plot_per_contact_envelope  (matplotlib)              │
└──────────────────────────────────────────────────────────────────┘
                                │
                                ▼ outputs to
                  <derivatives>/sub-X/…/efield/
                  ├─ m2m_<subject>/        (cached charm output if T1 supplied)
                  ├─ pair_a/               (FEM solve outputs for pair_a)
                  │   ├─ <sub>_TDCS_1_scalar.msh
                  │   └─ subject_volumes/<sub>_TDCS_1_scalar_E.nii.gz
                  ├─ pair_b/               (same for pair_b)
                  ├─ ti_envelope.msh       (mesh-attached envelope)
                  ├─ ti_envelope.nii.gz    (rasterized onto T1 grid)
                  ├─ ti_envelope_surface.npz  (portable for pyvista)
                  └─ ti_per_contact.tsv
```

### Why subprocess shell-out (the big deviation)

The original handoff specified `import simnibs` with lazy imports. That
doesn't work because SimNIBS's bundled Python and our venv's Python are
different versions and have separate compiled stacks. The implemented
pattern:

- `<simnibs_dir>/bin/charm <subID> <T1> [T2]` — direct CLI invocation
  (charm has no Python API entry point we benefit from anyway).
- `<simnibs_dir>/bin/simnibs_python -c "<inline script>"` — small inline
  Python snippets that build a `sim_struct.SESSION`, call
  `simnibs.utils.TI.get_maxTI`, or read mesh fields. Inputs/outputs are
  passed via JSON-encoded payloads and files on disk.
- All file I/O downstream (NIfTI sampling, plotting) happens in our
  venv. The portable `.npz` produced by `export_envelope_surface` is the
  bridge: surface points + cells + envelope scalars, no SimNIBS needed
  to render.

Trade-offs:

| Benefit | Cost |
|---|---|
| Two envs cleanly isolated; no version coupling | One subprocess per SimNIBS call (~100–500 ms overhead each) |
| User can upgrade SimNIBS without breaking project | Errors come back as captured stderr, not Python tracebacks |
| Pipeline keeps working in any installs that lack SimNIBS | Inline scripts are harder to debug than imported code |

If a future SimNIBS release publishes proper PyPI wheels with a Python
range that includes 3.10/3.12, the subprocess wrappers can collapse
back to in-process imports without changing the public function
signatures.

---

## 3. File-by-file map

### 3.1 New: [`src/ti_seeg/source/efield.py`](src/ti_seeg/source/efield.py)

Public surface (all in `__all__`):

| Function | Line | Side effects |
|---|---|---|
| `find_simnibs_dir(explicit=None) -> Path` | [efield.py:36](src/ti_seeg/source/efield.py:36) | Pure (filesystem reads). Searches: explicit > `$SIMNIBSDIR` (and parents) > `~/Applications/SimNIBS-*` > `/Applications/SimNIBS-*`. Raises `FileNotFoundError` if nothing matches. |
| `build_head_model(t1_path, t2_path, m2m_parent, subject_id, simnibs_dir, force=False) -> Path` | [efield.py:95](src/ti_seeg/source/efield.py:95) | Shells out to `charm`. Cwd set to `m2m_parent` so `m2m_<sub>/` lands there. Skips if `<sub>.msh` exists and `force=False`. |
| `template_m2m_dir(efield_template_path) -> Path` | [efield.py:131](src/ti_seeg/source/efield.py:131) | Resolve fallback head model. Raises with a useful pointer if `efield.template_m2m_dir` is unset. |
| `simulate_carrier_pair(m2m_dir, pair, out_dir, simnibs_dir, force=False) -> tuple[Path, Path]` | [efield.py:167](src/ti_seeg/source/efield.py:167) | One FEM solve. Returns `(mesh_path, nifti_path)`. Cached: skips if expected outputs already exist. |
| `compute_ti_envelope(field_a_msh, field_b_msh, out_dir, simnibs_dir, reference_volume=None) -> tuple[Path, Path]` | [efield.py:235](src/ti_seeg/source/efield.py:235) | Reads two SimNIBS meshes, calls `TI.get_maxTI`, writes `ti_envelope.msh` and (if `reference_volume`) `ti_envelope.nii.gz`. |
| `sample_efield_at_contacts(envelope_nifti, electrodes, radius_mm=2.0) -> pd.DataFrame` | [efield.py:290](src/ti_seeg/source/efield.py:290) | Pure numpy + nibabel. Sphere-mean per contact in voxel space. Returns `[name, envelope_mean, envelope_max, n_voxels]`. Skips NaN / 'n/a' / out-of-volume rows with one aggregated warning. |
| `export_envelope_surface(envelope_msh, out_path, simnibs_dir, grey_matter_tag=1002) -> Path` | [efield.py:359](src/ti_seeg/source/efield.py:359) | Shells out to extract grey-matter triangles + scalars to a portable `.npz`. Mesh tag is configurable (1002 is the SimNIBS 4 default). |

Private helpers:

- `_simnibs_python(simnibs_dir)` / `_charm_bin(simnibs_dir)` — path
  builders for the bundled binaries.
- `_run_simnibs_script(simnibs_dir, script, *, cwd=None)` —
  `subprocess.run([_simnibs_python, "-c", script], …)`. Captures
  stdout/stderr; raises `RuntimeError` with both streams on non-zero
  exit. Always log-debugs the captured stdout when present.
- `_expected_sim_outputs(out_dir, subid)` — predicts the
  SimNIBS-default output filenames so we can skip when cached.

### 3.2 New: [`src/ti_seeg/visualization/efield_plots.py`](src/ti_seeg/visualization/efield_plots.py)

| Function | Line | Notes |
|---|---|---|
| `plot_efield_orthoslice(envelope_nifti, t1_bg=None, threshold=None, title)` | [efield_plots.py:25](src/ti_seeg/visualization/efield_plots.py:25) | nilearn `plot_stat_map`. Background T1 dropped if file missing. |
| `plot_efield_3d_mesh(surface_npz, contacts_df=None, title, contact_radius_mm=2.0)` | [efield_plots.py:49](src/ti_seeg/visualization/efield_plots.py:49) | Reads `points`/`cells`/`scalars` from the npz. `pv.OFF_SCREEN=True` and `PYVISTA_OFF_SCREEN=true` set before instantiating the Plotter. Filters non-numeric contact coords. Returns a matplotlib Figure wrapping the pyvista screenshot (so `ReportBuilder.add_figure` works). |
| `plot_per_contact_envelope(per_contact, roi_groups=None, title)` | [efield_plots.py:124](src/ti_seeg/visualization/efield_plots.py:124) | Bar chart sorted desc by `envelope_mean`. Empty input → "No data" placeholder figure. Uses `set_xticks` + `set_xticklabels` to silence matplotlib warning. |

Importing this module **does not** import SimNIBS or pyvista. Pyvista is
only imported inside `plot_efield_3d_mesh`, with a clean `ImportError`
pointing at `uv sync --extra efield` when missing.

### 3.3 Modified: [`src/ti_seeg/config.py`](src/ti_seeg/config.py)

New pydantic models (`EfieldElectrode` at line [156](src/ti_seeg/config.py:156),
`EfieldCarrierPair` at line [172](src/ti_seeg/config.py:172),
`EfieldMontage` at line [179](src/ti_seeg/config.py:179),
`EfieldConfig` at line [184](src/ti_seeg/config.py:184)):

```python
class EfieldElectrode(BaseModel):
    name: str | None = None              # 10-20 atlas name OR
    position: list[float] | None = None  # [x, y, z] in subject MRI mm
    radius_mm: float = 12.0
    @field_validator("position")         # enforces 3-vector

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
    head_model_dir: str | None = None         # parent dir for m2m_<sub>; null -> efield/
    force_resegment: bool = False             # also forces re-FEM
    visualize_3d: bool = True
    contact_sampling_radius_mm: float = 2.0
    fallback_to_template: bool = True
    simnibs_dir: str | None = None            # /path/to/SimNIBS-4.x; null -> auto-discover
    template_m2m_dir: str | None = None       # required when t1_path is null + fallback_to_template
```

Other changes:

- `AnatomyConfig` gained `t2_path: str | None = None`
  ([config.py:150](src/ti_seeg/config.py:150)).
- `PipelineConfig.efield` field added between `connectivity` and `stats`
  ([config.py:221](src/ti_seeg/config.py:221)).
- `ReportConfig.include_sections` default now contains `"efield"`
  ([config.py:127](src/ti_seeg/config.py:127)).

### 3.4 Modified: [`src/ti_seeg/pipeline/run.py`](src/ti_seeg/pipeline/run.py)

- `AVAILABLE_STEPS` ([run.py:44](src/ti_seeg/pipeline/run.py:44)) now lists
  `"efield"` between `"anatomy"` and `"spectral"`.
- `STEP_REGISTRY` ([run.py:438](src/ti_seeg/pipeline/run.py:438))
  registers `_step_efield`.
- `_step_efield` ([run.py:158](src/ti_seeg/pipeline/run.py:158)):
  1. Short-circuit if `cfg.enabled is False` (default).
  2. Validate `cfg.montage is not None`.
  3. Resolve `simnibs_dir` via `find_simnibs_dir(cfg.simnibs_dir)`.
  4. Resolve head model: charm if `t1_path`, else `template_m2m_dir`,
     else raise.
  5. Run `simulate_carrier_pair` for `pair_a` then `pair_b` (cached).
  6. `compute_ti_envelope` → `.msh` + `.nii.gz`.
  7. `sample_efield_at_contacts` → `ti_per_contact.tsv` (only when
     NIfTI was produced, i.e., a reference T1 was available).
  8. `export_envelope_surface` → `ti_envelope_surface.npz` (best-effort;
     warns if it fails).
  9. Three plots into `report.html` under section `"efield"`. Each plot
     is in its own try/except so one viz failure doesn't kill the rest.

### 3.5 Modified: [`src/ti_seeg/source/__init__.py`](src/ti_seeg/source/__init__.py)

Re-exports the new public surface. Removed `compute_ti_field` from the
exports.

### 3.6 Modified: [`src/ti_seeg/source/localization.py`](src/ti_seeg/source/localization.py)

- Module docstring updated to point at `ti_seeg.source.efield`.
- Removed the `compute_ti_field` placeholder. `project_contact_values_to_t1`
  is unchanged.

### 3.7 Modified: [`src/ti_seeg/visualization/__init__.py`](src/ti_seeg/visualization/__init__.py)

Re-exports `plot_efield_3d_mesh`, `plot_efield_orthoslice`, `plot_per_contact_envelope`.

### 3.8 Modified: [`pyproject.toml`](pyproject.toml)

```toml
[project.optional-dependencies]
# SimNIBS itself is not on PyPI — install via the SimNIBS standalone installer
# and run this pipeline alongside it (the `efield` step shells out to charm /
# simnibs_python). The `efield` extra here only pulls the pip-installable peers.
efield = [
    "pyvista>=0.43",
]

[tool.pytest.ini_options]
markers = [
    "slow: long-running tests (FEM solve, segmentation)",
]
```

### 3.9 Modified: [`configs/analysis_defaults.yaml`](configs/analysis_defaults.yaml)

Adds an `efield:` block at the bottom (defaults) and `"efield"` to
`report.include_sections`.

### 3.10 Modified: [`configs/subject_template.yaml`](configs/subject_template.yaml)

`anatomy.t2_path` field + a fully-commented example `efield:` block at the
bottom.

### 3.11 New: [`tests/test_efield.py`](tests/test_efield.py)

13 tests:
- 3× `sample_efield_at_contacts` (in-volume / invalid-coords / no-xyz-cols)
- 4× `find_simnibs_dir` / `template_m2m_dir` filesystem behavior
- 4× visualization (orthoslice / per-contact bar empty / per-contact bar populated / 3D mesh — the last skips when pyvista isn't installed)
- 1× SimNIBS smoke (skipped if no install detected) — `simnibs_python --version`
- 1× `@pytest.mark.slow` full-pipeline smoke (skipped unless `$TI_SEEG_M2M_DIR` points at a complete m2m and SimNIBS is detected)

---

## 4. Configuration reference

Full schema with defaults (`configs/analysis_defaults.yaml` + per-subject overrides):

```yaml
anatomy:
  t1_path: null                    # /abs/path/to/T1.nii.gz; null -> use template
  t2_path: null                    # /abs/path/to/T2.nii.gz; optional, improves charm

efield:
  enabled: false                    # opt-in; expensive
  montage: null                     # required when enabled (see below)
  head_model_dir: null              # parent dir for m2m_<sub>/; null -> derivatives/efield/
  force_resegment: false            # re-run charm AND re-run FEM (clears caches)
  visualize_3d: true                # produce ti_envelope_surface.npz + 3D plot
  contact_sampling_radius_mm: 2.0
  fallback_to_template: true        # when t1_path is null
  simnibs_dir: null                 # null -> auto-discover via $SIMNIBSDIR / ~/Applications/SimNIBS-*
  template_m2m_dir: null            # required when fallback_to_template + t1_path null
```

Populated montage example (10–20 names; can also use `position: [x, y, z]`):

```yaml
efield:
  enabled: true
  montage:
    pair_a:
      anode:   { name: "F4", radius_mm: 12.0 }
      cathode: { name: "P4", radius_mm: 12.0 }
      current_mA: 1.0
      label: "carrier_2000Hz"
    pair_b:
      anode:   { name: "F8", radius_mm: 12.0 }
      cathode: { name: "P8", radius_mm: 12.0 }
      current_mA: 1.0
      label: "carrier_2130Hz"
  contact_sampling_radius_mm: 2.0
```

Note: `radius_mm` becomes the SimNIBS pad's half-width (the wrapper passes
`[radius_mm * 2, radius_mm * 2]` as the ellipse `dimensions`, with
4 mm `thickness` — these match SimNIBS tDCS-pad defaults).

---

## 5. How to run the step end-to-end

### 5.1 Prereqs

- SimNIBS 4.6 installed at `~/Applications/SimNIBS-*` (or set
  `efield.simnibs_dir` / `$SIMNIBSDIR`).
- A subject T1 NIfTI on disk (T2 optional but recommended).
- `uv sync` has succeeded against the project. For 3D plots:
  `uv sync --extra efield` (adds pyvista).

### 5.2 First-time charm (segmentation)

`charm` is **slow** (1–3 hr). It is the cached step — re-runs of the
pipeline reuse the m2m. You can either:

- **Let the pipeline run charm.** Set `anatomy.t1_path` (and `t2_path`)
  and run `ti-seeg run --steps efield`. The first invocation does
  charm + FEM + envelope + sampling end-to-end; the second is fast.
- **Run charm out-of-band first.** This is useful for the `@slow` test
  fixture or when iterating on stim configs:

  ```bash
  mkdir -p ~/efield_smoke && cd ~/efield_smoke
  /Users/ebrady/Applications/SimNIBS-4.6/bin/charm ernie \
      /Users/ebrady/Projects/TI_Toolbox/code/ti-toolbox/TI-Toolbox/sub-ernie/anat/sub-ernie_T1w.nii
  # produces ~/efield_smoke/m2m_ernie/
  ```

  Then point the pipeline at the existing m2m via
  `efield.head_model_dir: ~/efield_smoke` (its parent), or use it as the
  `efield.template_m2m_dir` for a fallback subject.

### 5.3 Full pipeline run

```bash
uv run ti-seeg run --config configs/subject_<id>.yaml --steps efield,report
```

Or run the full pipeline (efield is between anatomy and spectral):

```bash
uv run ti-seeg run --config configs/subject_<id>.yaml
```

Outputs land under `<derivatives_root>/sub-<id>/…/efield/` (see §2 diagram).

### 5.4 Slow integration test

```bash
TI_SEEG_M2M_DIR=~/efield_smoke/m2m_ernie uv run pytest -m slow tests/test_efield.py
```

Wall time: ~5–10 minutes per FEM solve; the test runs two solves plus
the envelope and sampling.

---

## 6. Outputs and what they mean

| Artifact | Generated by | Used by |
|---|---|---|
| `m2m_<sub>/` | `build_head_model` | All downstream steps; cached across runs. |
| `pair_<a\|b>/<sub>_TDCS_1_scalar.msh` | `simulate_carrier_pair` | `compute_ti_envelope` reads `field['E'].value` (V/m, per element). |
| `pair_<a\|b>/subject_volumes/<sub>_TDCS_1_scalar_E.nii.gz` | `simulate_carrier_pair` | Optional inspection; not used by later steps. |
| `ti_envelope.msh` | `compute_ti_envelope` | `export_envelope_surface` reads it. |
| `ti_envelope.nii.gz` | `compute_ti_envelope` (only if `reference_volume` supplied) | `sample_efield_at_contacts`, `plot_efield_orthoslice`. |
| `ti_envelope_surface.npz` | `export_envelope_surface` | `plot_efield_3d_mesh` in our venv. Keys: `points (N,3)`, `cells (M,3)`, `scalars (M,)`. |
| `ti_per_contact.tsv` | `sample_efield_at_contacts` | `plot_per_contact_envelope`; downstream stats notebooks. |
| `figures/efield_*.png` | `_step_efield` viz hooks | Embedded in `report.html` under section `efield`. |

`ti_per_contact.tsv` columns: `name`, `envelope_mean`, `envelope_max`,
`n_voxels`. Coordinates that were NaN, `"n/a"`, or fell outside the
volume are silently skipped with one aggregated warning.

---

## 7. Tests

```bash
uv run pytest -q                            # default: 38 pass, 1 skip
uv run pytest -m slow tests/test_efield.py  # slow smoke (needs $TI_SEEG_M2M_DIR)
uv run pytest tests/test_efield.py -v       # just the efield suite
```

Skip reasons you might see:
- `pyvista not installed` — install `--extra efield` to exercise the 3D
  mesh test.
- `SimNIBS not installed` — set `efield.simnibs_dir` or install SimNIBS.
- `TI_SEEG_M2M_DIR not set` — slow smoke needs a precomputed m2m.
- `head mesh missing: …` — slow smoke found the env var but the m2m
  folder doesn't have a finished `<sub>.msh`.

---

## 8. Known limitations and gotchas

### 8.1 Real ones from the implementation

1. **No bundled Ernie head.** SimNIBS 4.6 dropped the bundled m2m_ernie
   from `resources/`. The fallback path requires the user to supply
   `efield.template_m2m_dir`. The original handoff's `mni_template_m2m_dir()`
   helper was replaced with `template_m2m_dir(path)`.
2. **Subprocess overhead.** Each SimNIBS-side call takes ~100–500 ms
   just for interpreter startup. Negligible compared to FEM/charm wall
   time, but it adds up for tight loops. Don't call `compute_ti_envelope`
   in a hot loop without batching.
3. **Anisotropic conductivities not exposed.** The SimNIBS session is
   hardcoded to `tdcs.anisotropy_type = "scalar"`. Anisotropic (`"vn"`)
   would require DTI prep. Tracked as follow-up.
4. **Mesh tag for grey matter is hardcoded to 1002.** This is correct
   for SimNIBS 4.x but must be re-checked if upgrading. `export_envelope_surface`
   takes a `grey_matter_tag` arg as the escape hatch.
5. **Subprocess errors lose Python tracebacks.** When a SimNIBS-side
   inline script fails, the wrapper raises `RuntimeError` with the
   captured stdout+stderr. Helpful but not a Python traceback. Set
   the project logger to DEBUG to see the inline scripts being executed.
6. **`force_resegment=True` only forces charm + the FEM cache check.**
   It does **not** wipe `m2m_<sub>/` first; charm itself decides
   whether to re-run via `--forcerun`. If the m2m is corrupt, delete
   it manually.
7. **Headless pyvista on macOS.** `pv.OFF_SCREEN = True` and
   `PYVISTA_OFF_SCREEN=true` are set before instantiating the Plotter.
   On headless Linux you may need `xvfb-run` around the pipeline
   invocation.
8. **`compute_ti_envelope` uses `m_a` as the output mesh.** The
   envelope field is added back to mesh A and saved. Topologically
   identical to mesh B (same head model), but if you ever cross-mix
   pairs from different m2ms this will silently misalign — guard at
   call sites.
9. **`sample_efield_at_contacts` uses nearest-voxel indexing.** It
   doesn't trilinear-interpolate, then takes the mean inside a sphere of
   `radius_mm`. Acceptable at 1 mm isotropic; if the reference T1 is
   anisotropic the radius is converted to voxels per axis (see
   `r_vox = np.ceil(radius_mm / spacing)`).
10. **Coordinate frames must match.** The wrapper assumes `electrodes.tsv`
    `x/y/z` are in the same MRI space as the T1 used by `charm`. If they
    came from CT or atlas space, transform them first.
11. **Bare `except Exception` in the viz dispatch.** `_step_efield`
    wraps each plot call in `try/except Exception` so a single failure
    doesn't take down the rest. Pragmatic but coarse — could be tightened
    once we know which exceptions are routine.
12. **`pyproject.toml` still uses the deprecated `[tool.uv] dev-dependencies`
    field.** Pre-existing in this repo, not introduced by these PRs;
    triggers a uv warning on every invocation. Migrate to
    `[dependency-groups] dev = …`.

### 8.2 Charm-CWD trap (still relevant)

`charm` writes `m2m_<subID>/` into the current working directory. The
wrapper handles this via `subprocess.run(..., cwd=str(m2m_parent))`, but
if you ever invoke charm yourself outside the pipeline, pre-`cd` to the
desired parent directory.

### 8.3 EEG-position resolution

When the montage uses 10-20 names (e.g., `name: "F4"`), SimNIBS resolves
them via the m2m's `eeg_positions/EEG10-10_UI_Jurak_2007.csv`. If the
m2m wasn't built with EEG positions (older charm settings), set explicit
`position: [x, y, z]` instead.

---

## 9. Outstanding work

### 9.1 Step 7.7 — Real-MRI dry run on EMOP0649

This is what the next session should pick up.

Prereqs:
- EMOP0649 T1 (and ideally T2) lands in BIDS at the user's path. As of
  2026-05-08, paths in [`HANDOFF.md`](HANDOFF.md) v2 indicate the BIDS
  prep is done but MRI is still pending on a bigger machine.
- The user's stim-protocol notes — needed to fill the `<TBD>` electrode
  names in the EMOP0649 montage. The expected format is something like
  F3/F4 anodes + P3/P4 cathodes for 2000/2130 Hz carriers, but **don't
  guess** — confirm with the user.

Concrete steps (file paths assume current convention):

1. Add to `configs/subject_EMOP0649_run01.yaml` (and `_run02.yaml`):
   ```yaml
   anatomy:
     t1_path: /Users/ebrady/Projects/SEEG\ Processing/sub-EMOP0649/anat/sub-EMOP0649_T1w.nii.gz
     t2_path: /Users/ebrady/Projects/SEEG\ Processing/sub-EMOP0649/anat/sub-EMOP0649_T2w.nii.gz
   efield:
     enabled: true
     montage:
       pair_a:
         anode:   { name: "<TBD>", radius_mm: 12.0 }
         cathode: { name: "<TBD>", radius_mm: 12.0 }
         current_mA: 1.0
         label: "carrier_2000Hz"
       pair_b:
         anode:   { name: "<TBD>", radius_mm: 12.0 }
         cathode: { name: "<TBD>", radius_mm: 12.0 }
         current_mA: 1.0
         label: "carrier_2130Hz"
   ```
2. Optionally pre-run charm (1–3 hr) to decouple from the analysis run:
   ```bash
   cd <derivatives>/sub-EMOP0649/…/efield/   # or any parent dir
   /Users/ebrady/Applications/SimNIBS-4.6/bin/charm EMOP0649 \
       <T1 path> <T2 path>
   ```
3. Run the pipeline:
   ```bash
   uv run ti-seeg run --config configs/subject_EMOP0649_run01.yaml \
                       --steps anatomy,efield,report
   ```
4. Inspect `derivatives/.../report.html`. Acceptance:
   - Envelope hotspot is visibly near the stim target (amygdala for
     EMOP0649 inhibition block).
   - Per-contact bar chart ranks target-shank contacts at the top.
5. Update [`HANDOFF.md`](HANDOFF.md) §6 with findings and any tuning
   notes.

### 9.2 Follow-ups (file as separate issues)

- **Validation analysis** — predicted envelope vs. measured PLV-to-envelope
  per contact. Notebook, not pipeline plumbing.
- **Anisotropic conductivities** — wire `tdcs.anisotropy_type = "vn"`
  through, with a config knob and DTI prep step.
- **Interactive 3D viewer in the report** — `pyvista.Plotter.export_html`
  produces a self-contained widget; embedding in `mne.Report` is feasible
  but adds JS asset management.
- **Multi-pair / multi-frequency optimization** — search over montage
  space to maximize predicted target field. Research project, not
  pipeline.
- **Hippocampal subfield atlas (ASHS)** — finer-grained ROI coupling
  than shank-prefix. Tracked in `HANDOFF.md` v2 backlog.
- **Mypy + ruff sweep over efield.py and efield_plots.py** — no type
  errors expected, but the bare `except Exception` in `_step_efield`
  could use a tighter exception list.
- **Unit-test `_run_simnibs_script` error handling** — currently only
  exercised end-to-end; a contained test that injects a deliberately
  failing script would tighten coverage.
- **Migrate `[tool.uv] dev-dependencies` → `[dependency-groups] dev`** —
  silences the uv deprecation warning on every invocation.

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `FileNotFoundError: Could not locate a SimNIBS install` | No install at standard locations and `efield.simnibs_dir` unset | Set `efield.simnibs_dir: /path/to/SimNIBS-4.x` or `export SIMNIBSDIR=…` |
| `RuntimeError: simnibs_python script failed (exit 1)` with "ModuleNotFoundError: simnibs.utils.TI" | SimNIBS < 4.0 (the API isn't there) | Upgrade SimNIBS to 4.1+ |
| `RuntimeError: charm did not produce …<sub>.msh` | charm crashed mid-run | Check `m2m_<sub>/charm_log.html`, often a registration failure on bad MRI orientation. Try `--forceqform` (already passed) or fix the MRI |
| Empty 3D plot, white screen | Wrong grey-matter tag for the SimNIBS version | Inspect with `simnibs_python -c "from simnibs import mesh_io; m=mesh_io.read_msh('ti_envelope.msh'); import numpy as np; print(np.unique(m.elm.tag1))"` and pass `grey_matter_tag=…` to `export_envelope_surface` |
| `ImportError: pyvista is required for 3D E-field plots` | Optional dep not installed | `uv sync --extra efield` |
| Slow smoke skipped with "head mesh missing" | `$TI_SEEG_M2M_DIR` points at incomplete m2m | Run `charm` to completion first |
| Pipeline hangs at "Running FEM solve" with no output | SimNIBS is solving (5–10 min for cortex-only); not a hang | Watch `<out_dir>/simnibs_simulation/` for files appearing |

---

## 11. References

- Original planning handoff (this file's previous version): see git
  history before commit `b6f6e8a`.
- Tracking issue: [#11](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/issues/11).
- PRs: [#12](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/12),
  [#13](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/13),
  [#14](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/14),
  [#15](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/15),
  [#16](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/16),
  [#17](https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/pull/17).
- Grossman et al. (2017). "Noninvasive Deep Brain Stimulation via
  Temporally Interfering Electric Fields." *Cell* 169(6):1029–1041.
- SimNIBS 4 documentation: <https://simnibs.github.io/simnibs/>
- SimNIBS install guide:
  <https://simnibs.github.io/simnibs/build/html/installation/installation.html>
- pyvista off-screen rendering:
  <https://docs.pyvista.org/version/stable/user-guide/jupyter/>
- nilearn `plot_stat_map`:
  <https://nilearn.github.io/stable/modules/generated/nilearn.plotting.plot_stat_map.html>

---

## 12. First prompt for the next session

> "Picking up the TI E-field module on TI_SEEG_Analysis_Pipeline.
> Read `HANDOFF.md` (project state) and this file
> (`HANDOFF_EFIELD.md`) at the repo root. PRs #12–#17 implement
> steps 7.1–7.6 and are stacked off `main`; merge them in order
> (or wait for #12 to land and rebase the rest). The next concrete
> work is step 7.7 in §9.1 — the EMOP0649 dry run, blocked on (a)
> the user supplying real stim-electrode names for the `<TBD>`
> placeholders and (b) the EMOP0649 T1+T2 landing in BIDS. Do not
> kick off `charm` on a real subject without the user's go-ahead —
> it is 1–3 hours of compute and ~2 GB of disk per subject. Useful
> dev fixture: a precomputed Ernie m2m (the user's existing one in
> TI_Toolbox is incomplete; running charm on
> `/Users/ebrady/Projects/TI_Toolbox/code/ti-toolbox/TI-Toolbox/sub-ernie/anat/sub-ernie_T1w.nii`
> produces a usable m2m for the slow smoke). When in doubt, default
> behavior is `efield.enabled=false` — the rest of the pipeline runs
> unchanged."
