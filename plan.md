# TI_SEEG_Analysis_Pipeline — Implementation Plan

## Context

The user is building a single-subject SEEG analysis pipeline to characterize the spatiotemporal effects of **temporal interference (TI) stimulation** targeted at subcortical temporal-lobe structures (hippocampus, amygdala, temporal pole). Each subject has:

- **BIDS-formatted iEEG** (EDF raw, `electrodes.tsv` already localized, `events.tsv` with stim labels).
- **Patient-specific T1 MRI** (available if useful for visualization / anatomical mapping).
- **Two separate recordings per subject**, each with ~30 min baseline + task/stim:
  - **Block 1 (inhibition):** 2 kHz carriers, **130 Hz envelope** (gamma-range).
  - **Block 2 (excitation):** 2 kHz carriers, **5 Hz envelope** (theta-range).
- **Event labels** indicating baseline, stim-test, active-stim, and no-stim periods.

**Goal (v1):** Produce a modular, config-driven pipeline that gives a *rough but scientifically sound picture* of what TI is doing per subject — spectral power, time-frequency, phase entrainment to the envelope, cross-frequency coupling, within/cross-region connectivity, and anatomical visualization. Each analysis module must be runnable independently so the user can pick what to run. **v2** (future) will extend to group analyses and more complex methods (e.g., TI field modeling, hippocampal subfield atlases).

Repository will be created with the **GitHub CLI** as `TI_SEEG_Analysis_Pipeline`.

---

## Key scientific design decisions (derived from inputs)

1. **Carrier artifact handling.** Recording is continuous through stim, so the 2 kHz carriers (and their sum/harmonics) will dominate the signal during stim epochs. Pipeline must:
   - Apply tight notch filters at `f1`, `f2`, `f1+f2`, and harmonics up to Nyquist.
   - Extract the **TI envelope** via Hilbert of a bandpass around the difference frequency (5 Hz or 130 Hz) — this is the physiologically relevant driving signal.
   - Never low-pass below the envelope frequency when analyzing entrainment.
2. **Envelope-specific analyses.** The two blocks target different bands, so analyses must be parameterized per-block (theta-band for block 2, gamma-band for block 1). Cross-frequency coupling (theta-gamma PAC) is especially relevant for hippocampus and should be computed across-block where possible.
3. **SEEG re-referencing.** Bipolar (adjacent-contact) re-referencing on each shank is the standard — reduces volume-conduction and common-mode artifact without assuming a clean white-matter reference. Keep monopolar as an option.
4. **"Source localization" for SEEG.** True inverse modeling is not meaningful for intracranial electrodes — they already sample the source. "Source" in this pipeline means (a) mapping each contact to an anatomical label using the pre-localized `electrodes.tsv`, and (b) projecting contact-level results onto the patient's T1 / fsaverage for visualization. A stub for future **TI E-field modeling** (ROAST / SimNIBS) is included but not implemented in v1.
5. **Statistical contrasts.** Within-subject: active-stim vs. no-stim, active-stim vs. baseline, pre vs. during vs. post. Cluster-based permutation tests over time / frequency / contacts.

---

## Repository layout

```
TI_SEEG_Analysis_Pipeline/
├── pyproject.toml               # uv-managed, PEP 621
├── uv.lock
├── README.md                    # setup, BIDS layout expected, usage per module
├── .gitignore                   # ignores derivatives/, *.fif, *.edf, __pycache__, .venv
├── .github/workflows/ci.yml     # lint + tests on PR
├── configs/
│   ├── analysis_defaults.yaml   # default params for all modules
│   └── subject_template.yaml    # per-subject overrides (paths, stim freqs, ROI list)
├── src/ti_seeg/
│   ├── __init__.py
│   ├── config.py                # pydantic schema for YAML configs
│   ├── logging.py               # structured logger, run-id tagging
│   ├── io/
│   │   └── bids_loader.py       # mne_bids.read_raw_bids, electrodes/events readers
│   ├── preprocessing/
│   │   ├── filters.py           # notch (line + carriers + harmonics), bandpass
│   │   ├── artifacts.py         # bad-channel detection, flat/noisy metrics
│   │   └── referencing.py       # bipolar-on-shank, monopolar, CAR options
│   ├── events/
│   │   └── epochs.py            # parse events.tsv -> condition epochs + sliding
│   ├── anatomy/
│   │   └── contacts.py          # group contacts by region, ROI masks, 3D plots
│   ├── spectral/
│   │   └── psd.py               # multitaper + Welch PSDs per condition
│   ├── tfr/
│   │   └── tfr.py               # Morlet + multitaper TFR, baseline normalization
│   ├── phase/
│   │   ├── envelope.py          # Hilbert-based TI-envelope extractor
│   │   ├── entrainment.py       # ITC, PLV of neural signal to TI envelope
│   │   └── cfc.py               # phase-amplitude coupling (Tort MI, mean vector)
│   ├── connectivity/
│   │   └── connectivity.py      # coherence, wPLI, PLV matrices via mne-connectivity
│   ├── source/
│   │   └── localization.py      # anatomical mapping + T1 visualization (+ stub for E-field)
│   ├── visualization/
│   │   └── plots.py             # contact-on-brain, PSD, TFR, matrices, HTML report
│   ├── stats/
│   │   └── contrasts.py         # cluster-permutation tests between conditions
│   └── pipeline/
│       └── run.py               # orchestrator: run modules in sequence per config
├── scripts/                     # thin CLI wrappers (also exposed via pyproject.scripts)
│   ├── run_preprocessing.py
│   ├── run_spectral.py
│   ├── run_tfr.py
│   ├── run_phase.py
│   ├── run_connectivity.py
│   ├── run_anatomy.py
│   ├── run_stats.py
│   └── run_full_pipeline.py
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   └── 02_single_subject_report.ipynb
└── tests/                       # pytest; synthetic + tiny real fixtures
    ├── conftest.py
    ├── test_io.py
    ├── test_filters.py
    ├── test_envelope.py
    ├── test_epochs.py
    ├── test_spectral.py
    ├── test_tfr.py
    ├── test_phase.py
    └── test_connectivity.py
```

Derivative outputs (per subject, per run) go to `derivatives/ti_seeg/sub-XX/ses-YY/` following BIDS-Derivatives, with a snapshot of the resolved config saved alongside every figure / `.h5` result.

---

## Dependencies (pyproject.toml)

Core: `mne>=1.7`, `mne-bids`, `mne-connectivity`, `numpy`, `scipy`, `pandas`, `matplotlib`, `nibabel`, `pybids`, `h5py`, `pyyaml`, `pydantic>=2`, `tqdm`, `click` (CLI), `joblib` (parallel).
Optional extras: `nilearn` (anatomical plotting), `seaborn`, `jupyterlab`.
Dev: `pytest`, `pytest-cov`, `ruff`, `mypy`, `pre-commit`.

---

## Module-by-module implementation detail

### 1. `io/bids_loader.py`
- `load_subject(bids_root, subject, session, task, run) -> Raw`: wraps `mne_bids.read_raw_bids`.
- `load_electrodes(bids_root, subject) -> pd.DataFrame`: reads `electrodes.tsv` with anatomical labels; validates coord frame.
- `load_events(raw) -> pd.DataFrame`: parses `events.tsv` via mne-bids, normalizes labels (`baseline`, `stim_test`, `active_stim`, `no_stim`) into a controlled vocabulary.
- Validation: sampling rate ≥ 4× highest carrier, channel count matches electrodes.tsv, coord frame is documented.

### 2. `preprocessing/`
- **`filters.py`:** IIR notch (MNE `raw.notch_filter`) at line noise (50/60 Hz + harmonics to Nyquist), then at `f1`, `f2`, `f1+f2`, and harmonics. Optional broad bandpass (0.5 Hz – 0.45·fs). Zero-phase FIR fallback for envelope-band filtering.
- **`artifacts.py`:** Per-channel flatness / variance / kurtosis detectors; compare post- vs. pre-stim variance ratio to flag channels saturating during stim. Writes `bad_channels.json`.
- **`referencing.py`:** `bipolar_on_shank(raw, electrodes_df)` — parses contact names (e.g., `LAH1, LAH2 …`) into shanks and creates bipolar derivations of adjacent contacts. Also supports common-average and monopolar pass-through.

### 3. `events/epochs.py`
- `make_condition_epochs(raw, events_df, conditions, tmin, tmax)` — returns dict of `mne.Epochs` per condition.
- `make_sliding_epochs(raw, window, overlap)` — for continuous TFR / connectivity.
- Baseline epochs drawn from the pre-stim 30 min.

### 4. `anatomy/contacts.py`
- Group channels by `electrodes.tsv` anatomical label column (falls back to user-provided ROI map).
- `get_roi_channels(df, roi)` for analyses like "hippocampus only".
- 3D visualization: contacts on patient T1 via `mne.viz.plot_alignment` + `nilearn.plotting.view_markers` for browser-friendly output. fsaverage fallback if patient T1 not configured.

### 5. `spectral/psd.py`
- `compute_psd(epochs, method={'multitaper','welch'}, fmin, fmax)` using `mne.time_frequency.psd_array_multitaper` / `psd_array_welch`.
- Band aggregation: delta, theta (with 5 Hz isolation), alpha, beta, low-gamma, high-gamma (with 130 Hz isolation), plus user-defined bands from config.
- Returns tidy DataFrame (channel × band × condition).
- Contrasts: log-ratio PSD (active / no_stim, active / baseline).

### 6. `tfr/tfr.py`
- Morlet TFR (`mne.time_frequency.tfr_morlet`) with log-spaced frequencies 2–200 Hz.
- Multitaper TFR for narrowband envelope targets (5 Hz, 130 Hz).
- Baseline normalization: log-ratio against pre-stim baseline.
- Output: per-condition `AverageTFR` saved to `.h5`.

### 7. `phase/`
- **`envelope.py`:** `extract_ti_envelope(raw, f_env, bandwidth)` — bandpass around envelope freq, Hilbert, return amplitude envelope + instantaneous phase as a reference "stimulus" channel. (Because SEEG records the TI beat directly, this gives a ground-truth phase to lock against.)
- **`entrainment.py`:**
  - **ITC** to active-stim onset (`mne.time_frequency.tfr_morlet` with `return_itc=True`).
  - **PLV-to-envelope**: for each channel, bandpass-Hilbert at envelope freq, compute `|⟨exp(i·(φ_channel − φ_envelope))⟩|`.
  - Surrogate distribution by time-shifting envelope for significance.
- **`cfc.py`:** Tort modulation index (MI) and mean-vector length for phase-amplitude coupling. Primary targets: theta (5 Hz ± 2) phase × high-gamma (80–150 Hz) amplitude in block 2; similar analyses in hippocampal ROIs.

### 8. `connectivity/connectivity.py`
- `mne_connectivity.spectral_connectivity_epochs` for coherence, imaginary coherence, PLV, wPLI in configured bands.
- Matrices per condition + contrasts; within-ROI and between-ROI summaries (e.g., hippocampus ↔ amygdala).

### 9. `source/localization.py`
- v1: anatomical lookup + projection onto T1 / fsaverage for visualization (effect maps as colored markers).
- v2 stub: `compute_ti_field(t1, electrodes, currents) -> NotImplementedError("Planned: SimNIBS/ROAST integration")`.

### 10. `stats/contrasts.py`
- Wrappers around `mne.stats.permutation_cluster_test` / `permutation_cluster_1samp_test` for TFR and PSD contrasts, corrected across channels/frequencies/time.

### 11. `visualization/plots.py` + HTML report
- `mne.Report` assembly pulling figures from each module.
- Standard plots: bad-channel QC, PSD per condition, TFR per ROI, PLV-to-envelope topoplots on 3D brain, connectivity matrices, CFC comodulograms.

### 12. `pipeline/run.py` + CLI
- `ti-seeg run --config configs/subject_XX.yaml --steps preprocessing,spectral,tfr,phase,connectivity,report`
- Individual steps also callable: `ti-seeg spectral --config ...`
- Each step writes a deterministic output path and a `run_manifest.json` (git SHA, config hash, timestamp, module versions).

---

## Config schema (pydantic)

- `subject`, `session`, `task`, `run`, `bids_root`, `derivatives_root`.
- `ti`: `{f1_hz, f2_hz, envelope_hz, block_label}`.
- `preprocessing`: `{line_freq, notch_harmonics, bandpass, reference: 'bipolar'|'car'|'monopolar', bad_channel_strategy}`.
- `events`: condition → label mapping, epoch windows.
- `rois`: list of anatomical labels grouped by target (hippocampus, amygdala, temporal_pole, …).
- Per-module blocks (`spectral`, `tfr`, `phase`, `connectivity`, `stats`) with enable flags + parameters.

---

## Repository bootstrap steps (Github CLI)

1. `gh repo create TI_SEEG_Analysis_Pipeline --private --clone` (**private**, per user decision).
2. `uv init --package` then `uv add` the dependency set above; `uv sync`.
3. Scaffold the directory tree + empty module files with minimal `__init__.py`s.
4. Add `.gitignore`, `pyproject.toml` metadata, `README.md` (setup + BIDS layout + per-module usage), `LICENSE` (**MIT**), `.pre-commit-config.yaml` (ruff + mypy).
5. Add CI workflow: `pytest -q`, `ruff check`, `mypy src/`.
6. Initial commit + push to `main`.
7. Implement modules in the phased order below, one logical commit per phase, pushed to `main` (solo repo — feature branches / PRs unnecessary for v1 unless the user prefers them later).

---

## Phased delivery order

**All of phases A–D are in v1** (per user decision). Phase E remains a v2 stub only.

- **Phase A (foundation):** repo bootstrap, config schema, `io`, `preprocessing`, `events`, `anatomy`, tests + tiny synthetic fixture, HTML report skeleton.
- **Phase B (core analyses):** `spectral`, `tfr`, `phase/envelope`, `phase/entrainment`.
- **Phase C (advanced analyses):** `phase/cfc`, `connectivity`, `stats` contrasts.
- **Phase D (visualization & polish):** 3D anatomical plots, full HTML report, notebook walkthrough.
- **Phase E (future / v2 stubs, NOT implemented in v1):** E-field modeling integration (SimNIBS/ROAST), multi-subject group stats.

---

## Critical files to be created

All files under `src/ti_seeg/` listed in the layout, `configs/analysis_defaults.yaml`, `configs/subject_template.yaml`, `scripts/run_*.py`, `tests/*`, `pyproject.toml`, `.github/workflows/ci.yml`, `README.md`.

## Reusable libraries (no reimplementation)

- `mne-bids.read_raw_bids` — BIDS iEEG loading.
- `mne.io.Raw.notch_filter` / `.filter` — filtering.
- `mne.set_bipolar_reference` — bipolar derivations.
- `mne.time_frequency.tfr_morlet`, `psd_array_multitaper` — TFR / PSD.
- `mne_connectivity.spectral_connectivity_epochs` — connectivity.
- `mne.stats.permutation_cluster_test` — statistics.
- `mne.Report` — HTML reporting.
- `nilearn.plotting` — anatomical visualization.

---

## Verification plan

1. **Unit tests (synthetic data):** generate a `RawArray` with an injected 5 Hz envelope on a 2 kHz carrier and verify: (a) notch removes carriers, (b) envelope extractor recovers 5 Hz amplitude/phase, (c) PLV-to-envelope ≈ 1 for the "driven" channel and ≈ 0 for noise channels, (d) epoching produces the expected number of active/no-stim epochs from a known events table.
2. **Tiny BIDS fixture:** a ≤30 s synthetic BIDS subject committed under `tests/data/` exercised end-to-end in `test_pipeline.py` to confirm config → preprocessing → spectral/TFR → report runs cleanly.
3. **Real-data smoke test:** run `ti-seeg run --config configs/subject_<real>.yaml --steps preprocessing,spectral,tfr,phase --rois hippocampus,amygdala,temporal_pole` on the first real subject. Inspect HTML report for: carriers removed, baseline PSD plausible, ITC/PLV peaks at 5 Hz (block 2) and 130 Hz (block 1) in target ROIs, no crashes across conditions.
4. **CI:** `ruff`, `mypy`, `pytest` pass on PR before merge.
5. **Reproducibility check:** re-running the same config on the same raw data produces byte-identical derivative hashes (or documented non-determinism with reasons).
