# TI_SEEG_Analysis_Pipeline — Handoff document

> **Purpose of this file:** This document is a self-contained briefing so a fresh
> Claude instance (or human collaborator) can pick up this project without
> needing the prior conversation history. It captures goals, decisions, current
> state (what's done, what's broken, what's outstanding), and the next concrete
> steps to take.
>
> **Last updated:** 2026-04-24

---

## 0. TL;DR for the next instance

- Private GitHub repo **`bradyevan110/TI_SEEG_Analysis_Pipeline`** is created and code is pushed.
- Full pipeline scaffold is written: config schema, BIDS I/O, preprocessing (filters/bad-channels/re-ref), epoching, anatomy/ROI grouping, spectral PSD, TFR, phase envelope, entrainment (PLV-to-reference with surrogates), cross-frequency coupling (Tort MI), connectivity (coh/wPLI/PLV), cluster-permutation stats, HTML report builder, CLI (`ti-seeg`), per-module CLI scripts, a walkthrough notebook, and unit tests.
- `uv sync --all-extras` succeeded. Dependencies resolved with MNE 1.10, mne-bids, mne-connectivity, pydantic 2, click, nilearn, seaborn, etc.
- **Tests: 24/25 passing.** One test fails because of a numerical-instability bug in `bandpass_hilbert` when the band is narrow relative to sfreq (see §6).
- **Not yet done:** fix the filter bug, run `ruff format` / `mypy`, exercise the pipeline on a real BIDS subject, flesh out the notebook with real outputs, and polish HTML-report visuals.

---

## 1. Project context

Single-subject SEEG analysis pipeline for **temporal interference (TI) stimulation** studies. The target application is characterizing spatiotemporal neural effects of TI targeted at subcortical temporal-lobe structures (hippocampus, amygdala, temporal pole).

### Experimental paradigm (assumed per subject)

- **Two recordings per subject**, one per stim block.
  - **Block 1 (inhibition):** 2 kHz carriers, **130 Hz envelope** (gamma-range).
  - **Block 2 (excitation):** 2 kHz carriers, **5 Hz envelope** (theta-range).
- Each recording contains ~30 min of baseline pre-stim, then active-stim / no-stim / stim-test periods labeled in `events.tsv`.
- Recording is **continuous through stim** — so carrier artifacts at ~2 kHz dominate during stim epochs and must be notched aggressively.

### BIDS layout assumed

```
<bids_root>/sub-XX/ses-YY/ieeg/
    sub-XX_ses-YY_task-<task>_run-<NN>_ieeg.edf
    sub-XX_ses-YY_task-<task>_run-<NN>_ieeg.json
    sub-XX_ses-YY_task-<task>_run-<NN>_channels.tsv
    sub-XX_ses-YY_task-<task>_run-<NN>_events.tsv
    sub-XX_ses-YY_space-<space>_electrodes.tsv    # pre-localized + anat labels
    sub-XX_ses-YY_space-<space>_coordsystem.json
```

`electrodes.tsv` MUST have an anatomical-label column (e.g., from FreeSurfer aparc+aseg). Patient-specific T1 is optional and only used for visualization.

---

## 2. Decisions locked in (do not reopen without user input)

| Decision              | Choice                       |
| --------------------- | ---------------------------- |
| Repo visibility       | Private                      |
| License               | MIT                          |
| v1 scope              | Phases A–D (all shipped)     |
| Package manager       | `uv` + `pyproject.toml`      |
| Python versions       | ≥ 3.10                       |
| Reference scheme      | Bipolar on-shank (default)   |
| Event labels          | `baseline`, `stim_test`, `active_stim`, `no_stim` (canonical) |
| Source localization   | Anatomical lookup + T1 projection only (no inverse modeling; E-field modeling is v2 stub) |
| Commit strategy (v1)  | Direct to `main` on this solo repo (no feature branches / PR flow) |

### Explicit non-goals for v1

- True source-space inverse modeling (meaningless for intracranial electrodes).
- Multi-subject group statistics.
- TI E-field modeling via SimNIBS/ROAST (stub raises `NotImplementedError` — planned for v2).

---

## 3. Repository layout (actual, after push)

```
TI_SEEG_Analysis_Pipeline/
├── HANDOFF.md                  ← this file
├── README.md
├── LICENSE                     ← MIT
├── pyproject.toml              ← hatchling build + ruff + mypy + pytest config
├── uv.lock
├── .gitignore                  ← ignores raw data, derivatives, subject_* configs
├── .pre-commit-config.yaml     ← ruff lint + format
├── .github/workflows/ci.yml    ← ubuntu+macos, py3.11, ruff+mypy+pytest
├── configs/
│   ├── analysis_defaults.yaml  ← all default parameters
│   └── subject_template.yaml   ← copy-me template for per-subject configs
├── src/ti_seeg/
│   ├── __init__.py             ← __version__ = "0.1.0"
│   ├── config.py               ← pydantic schema + YAML loader + deep-merge
│   ├── logging.py              ← run-id-tagged structured logger
│   ├── utils.py                ← manifest writing, ROI matching, hashing
│   ├── cli.py                  ← click entry point `ti-seeg`
│   ├── io/
│   │   └── bids_loader.py      ← mne_bids.read_raw_bids + electrodes/events
│   ├── preprocessing/
│   │   ├── filters.py          ← notch (line + TI carriers + f1+f2 + harmonics) + bandpass
│   │   ├── artifacts.py        ← flatness / variance-z / kurtosis-z bad-channel detector
│   │   └── referencing.py      ← bipolar-on-shank / CAR / monopolar
│   ├── events/
│   │   └── epochs.py           ← condition-locked + sliding epochs
│   ├── anatomy/
│   │   └── contacts.py         ← ROI grouping from electrodes.tsv labels
│   ├── spectral/
│   │   └── psd.py              ← multitaper/Welch PSD + band aggregation + log-ratio contrast
│   ├── tfr/
│   │   └── tfr.py              ← Morlet / multitaper TFR + baseline logratio
│   ├── phase/
│   │   ├── envelope.py         ← bandpass + Hilbert → amplitude + phase (+ TI-envelope wrapper)
│   │   ├── entrainment.py      ← PLV-to-reference + time-shift surrogate p-values
│   │   └── cfc.py              ← Tort modulation index for phase-amplitude coupling
│   ├── connectivity/
│   │   └── connectivity.py     ← mne-connectivity wrapper (coh/wpli/plv), band-averaged
│   ├── stats/
│   │   └── contrasts.py        ← cluster_permutation_test wrappers
│   ├── source/
│   │   └── localization.py     ← contact-level projection to T1 volume + v2 E-field stub
│   ├── visualization/
│   │   ├── plots.py            ← PSD, TFR heatmap, connectivity matrix, 2D contact scatter
│   │   └── report.py           ← `ReportBuilder` (wraps mne.Report) that collects figs
│   └── pipeline/
│       └── run.py              ← step orchestrator: `run_pipeline(cfg, steps)`
├── scripts/
│   ├── run_full_pipeline.py    ← thin wrapper → `ti-seeg run`
│   ├── run_preprocessing.py
│   ├── run_spectral.py
│   ├── run_tfr.py
│   ├── run_phase.py
│   ├── run_connectivity.py
│   ├── run_anatomy.py
│   └── run_stats.py
├── notebooks/
│   └── 01_single_subject_walkthrough.ipynb
└── tests/
    ├── conftest.py             ← synthetic RawArray + events + minimal config fixtures
    ├── test_config.py
    ├── test_filters.py
    ├── test_referencing.py
    ├── test_envelope.py        ← 1 FAILING test (see §6)
    ├── test_entrainment.py
    ├── test_cfc.py
    ├── test_epochs.py
    ├── test_anatomy.py
    ├── test_spectral.py
    └── test_cli.py
```

---

## 4. Pipeline design — how the pieces fit

### Config flow

1. User copies `configs/subject_template.yaml` → `configs/subject_<id>_block<N>.yaml` and fills in paths, TI stim parameters, ROI map.
2. `ti_seeg.config.load_config(path)` reads the subject YAML, reads its `defaults_file` (default: `configs/analysis_defaults.yaml`), deep-merges (subject overrides defaults), and returns a validated `PipelineConfig` (pydantic v2 model).
3. The CLI and all scripts accept `--config <path>`.

### Step orchestrator

`ti_seeg.pipeline.run.run_pipeline(config, steps)` is the main entry point. It:

1. Creates `<derivatives_root>/sub-XX/ses-YY/task-<t>_run-<n>/`.
2. Snapshots the resolved config into `config_snapshot.yaml`.
3. Initializes a `ReportBuilder`.
4. Runs each step in order; writes a `run_manifest.json` entry per step.

**Available steps** (in `STEP_REGISTRY`):

| Step            | Reads                                 | Writes                                                          |
| --------------- | ------------------------------------- | --------------------------------------------------------------- |
| `preprocessing` | BIDS raw                              | `preprocessed_raw.fif`, `bad_channels.json`, QC figure          |
| `anatomy`       | `electrodes.tsv`, preprocessed raw    | ROI groups + anatomy section in report                          |
| `spectral`      | preprocessed raw → epochs             | `spectral/band_power.tsv`, PSD figures per condition            |
| `tfr`           | epochs                                | `tfr/tfr_<cond>-tfr.h5`, ROI-mean TFR figures                   |
| `phase`         | `active_stim` epochs                  | `phase/plv_to_envelope.tsv`                                     |
| `cfc`           | epochs                                | `phase/cfc_mi_<cond>.tsv`                                       |
| `connectivity`  | epochs                                | `connectivity/con_<method>_<band>_<cond>.npz` + figures         |
| `stats`         | epochs (active_stim vs no_stim)       | logs cluster test stats                                         |
| `report`        | accumulated figures                   | `report.html`                                                   |

The `RunContext` (dataclass in `run.py`) caches the preprocessed raw and condition epochs between steps in one process, and lazily loads `preprocessed_raw.fif` from disk if a later step is run in a separate invocation.

### Key scientific choices baked into the code

1. **Carrier notching:** `carrier_notch_freqs` emits `[f1, 2f1, ..., f2, 2f2, ..., f1+f2, ...]`. The envelope frequency is intentionally *not* notched so entrainment is preserved.
2. **TI envelope extraction:** `extract_ti_envelope` bandpasses around `f_env` then Hilberts. Because the difference product of two 2 kHz carriers shows up as a **direct** spectral component at |f1 − f2| once measured intracranially near the stim site, this recovers a reference phase to phase-lock against. For cleaner references a dedicated stim-monitor channel or the mean of high-amplitude contacts can be used (see `_step_phase` in `pipeline/run.py`).
3. **PLV-to-envelope with surrogates:** `plv_to_reference_with_surrogates` builds a null distribution by time-shifting the reference (minimum shift = 10% of signal length). **Caveat:** for perfectly periodic references (pure sinusoid, no noise), time-shift surrogates do not break the phase relationship — see §6 note.
4. **Bipolar on-shank rereferencing:** `parse_shank` extracts `(shank_prefix, contact_index)` from names like `LAH1`, `RAmy12`, `LAH01`. `bipolar_pairs_from_shanks` pairs contacts with consecutive indices on the same shank. `apply_reference` uses `mne.set_bipolar_reference`.
5. **Cluster-permutation stats:** `paired_condition_tfr_contrast` runs `mne.stats.permutation_cluster_test` on per-epoch Morlet TFRs between `active_stim` and `no_stim` for a single channel. Multi-channel extension is straightforward (pass `connectivity` argument).

---

## 5. How to run / develop

```bash
# From repo root:
cd /Users/ebrady/Projects/TI_SEEG_Analysis_Pipeline
brew shellenv | source  # if uv isn't on PATH
uv sync --all-extras

# Run tests:
uv run pytest

# Format + lint (not yet applied to the tree):
uv run ruff format .
uv run ruff check --fix .
uv run mypy src/       # advisory in v1 (CI has `continue-on-error: true`)

# Validate a config:
uv run ti-seeg validate configs/subject_template.yaml

# List available steps:
uv run ti-seeg steps

# Run the full pipeline for one subject:
uv run ti-seeg run --config configs/subject_001_block1.yaml

# Run a subset:
uv run ti-seeg run --config configs/subject_001_block1.yaml --steps preprocessing,spectral,tfr
```

---

## 6. Known bug: numerical instability in `bandpass_hilbert`

**Symptom:** when `bandpass_hilbert` is called with a narrow band (e.g., 4–6 Hz) at a high sampling rate (2 kHz), `scipy.signal.filtfilt` on the Butterworth transfer function returns astronomically large values (~1e137). This kills `extract_ti_envelope` output.

**Evidence:**

```text
amp stats: 2.5056161028368855e+137 8.960500154772468e+137
phase rate (Hz): -0.056       # expected 5.0
```

(Reproduced via `uv run python -c "..."` during test debugging.)

**Root cause:** the Butterworth `butter(order=4, [4/1000, 6/1000], btype='band')` produces `(b, a)` coefficients whose direct-form realization is numerically unstable for this narrow band. Standard fix is **second-order sections (SOS)** form.

**Recommended fix (in `src/ti_seeg/phase/envelope.py`):**

```python
from scipy.signal import butter, sosfiltfilt, hilbert

def bandpass_hilbert(
    data: np.ndarray,
    sfreq: float,
    f_center: float,
    bandwidth: float,
    order: int = 4,
) -> tuple[np.ndarray, np.ndarray]:
    lo = max(0.1, f_center - bandwidth / 2.0)
    hi = min(0.49 * sfreq, f_center + bandwidth / 2.0)
    if hi <= lo:
        raise ValueError(f"Invalid band [{lo}, {hi}] for sfreq={sfreq}")
    sos = butter(order, [lo / (sfreq / 2), hi / (sfreq / 2)], btype="band", output="sos")
    filtered = sosfiltfilt(sos, data, axis=-1)
    analytic = hilbert(filtered, axis=-1)
    return np.abs(analytic), np.angle(analytic)
```

**Verification:** after applying the fix, re-run `uv run pytest` — `test_envelope_recovers_direct_reference_signal` should pass (phase rate will come out to ≈ 5 Hz) and `test_bandpass_hilbert_2d_input` will stay green.

**Also revisit:** this bug may have been silently affecting `cfc.py` (which uses the same helper) and the pipeline's phase step. Once fixed, re-run `test_entrainment.py` and `test_cfc.py` to confirm results are sensible.

### A secondary envelope concern (not a bug, but document it)

If `extract_ti_envelope` is ever called on a true TI-stimulus signal (sum of two carriers at ~2 kHz), bandpassing around `f_env` will NOT recover the envelope, because the AM product's spectral content sits at `carrier ± f_env`, not at `f_env` itself. For that case, the correct demodulation is:

1. Hilbert the full signal → amplitude envelope.
2. Bandpass the amplitude envelope around `f_env`.

The current `_step_phase` in `pipeline/run.py` computes a mean reference by averaging across channels and bandpassing at `f_env` — this works if contacts near the stim site record the envelope as a direct spectral component (which they typically do in SEEG, by virtue of tissue rectification / nonlinearities). For a stim-monitor channel in hardware, the envelope is already there directly. Both assumptions should be validated against the first real recording.

---

## 7. Test status

**Passing (24):** `test_config.py` (4), `test_filters.py` (2), `test_referencing.py` (3), `test_envelope.py` (1 of 2), `test_entrainment.py` (2), `test_cfc.py` (1), `test_epochs.py` (3), `test_anatomy.py` (4), `test_spectral.py` (2), `test_cli.py` (2).

**Failing (1):** `tests/test_envelope.py::test_envelope_recovers_direct_reference_signal` — blocked on §6. Fix the filter, re-run pytest.

**Warning to address:** `test_filters.py::test_notch_attenuates_injected_carrier` emits a `RuntimeWarning: filter_length is longer than the signal` from MNE's notch. Either lengthen the synthetic raw in `conftest.py` (currently 4 s at 8192 Hz) or shorten the notch filter. Not a failure, but should be cleaned up.

---

## 8. What remains before v1 can be called "done"

1. **Fix the filter bug** (§6). Verify all 25 tests pass.
2. **`ruff format .`** on the full tree and commit the formatting pass.
3. **`ruff check --fix .`** and resolve any remaining lint errors.
4. **Run `mypy src/`** and fix obvious type errors (strict mode is off by design).
5. **Dry-run the pipeline on a real BIDS subject** (the user's first recording). Look in the generated `report.html` for:
   - Carrier frequencies removed from PSD.
   - Plausible baseline PSD shape (1/f-ish).
   - ITC/PLV peaks at 5 Hz in block 2 and 130 Hz in block 1 within target ROIs.
   - No crashes across conditions.
6. **Flesh out the notebook** (`notebooks/01_single_subject_walkthrough.ipynb`) with real outputs from step 5 so it serves as living documentation.
7. **Polish the HTML report**: group figures by section clearly, add text commentary per section, include the config snapshot as a collapsible block.
8. **Exercise `source/localization.py::project_contact_values_to_t1`** with a real T1 once anatomy is wired up — currently it's untested.
9. **Write an end-to-end test** that builds a tiny (≤30 s) synthetic BIDS subject in `tests/data/` and runs `run_pipeline` through all steps with `report` disabled. This is the highest-value test to add post-fix.
10. **Fix the deprecation warning** from `[tool.uv.dev-dependencies]` (`pyproject.toml` bottom) — switch to `[dependency-groups.dev]` per uv's migration guidance.

### Nice-to-have / v2 backlog

- Multi-subject group stats.
- SimNIBS/ROAST E-field modeling in `source/localization.py::compute_ti_field`.
- Hippocampal subfield atlas (ASHS) integration in anatomy grouping.
- Replace the 2D glass-brain scatter with nilearn/pyvista 3D brain plots.
- Parallelize across epochs/conditions via `joblib` where it helps (currently serial).

---

## 9. Style rules baked into this codebase

- **No comments unless the *why* is non-obvious.** Readable names over comments.
- **No unnecessary error handling, fallbacks, or validation.** We trust internal code; only validate at system boundaries (BIDS I/O, config loading).
- **No preemptive abstraction** — three similar lines is better than a bad abstraction.
- **Private state goes in `__init__.py`s explicitly listed in `__all__`** so module public API is obvious.
- **Pydantic v2** for all configs. Extend `PipelineConfig` in `src/ti_seeg/config.py` when adding new parameters; never pass bare dicts deeper than the CLI.
- **Logging:** use `ti_seeg.logging.get_logger("module.name")` — this inherits the run-id tagged formatter configured by `setup_logger`.

---

## 10. Concrete first prompt for the next Claude instance

> "I'm handing off work on TI_SEEG_Analysis_Pipeline (private repo bradyevan110/TI_SEEG_Analysis_Pipeline). Read `HANDOFF.md` at the repo root first — it has the current state, decisions, and the outstanding filter bug. Starting point: fix the numerical instability in `src/ti_seeg/phase/envelope.py::bandpass_hilbert` (switch to SOS form as described in §6), verify all 25 tests pass with `uv run pytest`, then run `ruff format .` and commit the formatted tree. After that, let me know before you start a real-data dry run."
