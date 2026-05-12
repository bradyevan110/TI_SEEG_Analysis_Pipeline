# TI_SEEG_Analysis_Pipeline

A modular SEEG analysis pipeline for characterizing the spatiotemporal effects of **temporal interference (TI) stimulation** targeted at subcortical temporal-lobe structures (hippocampus, amygdala, temporal pole, etc.). Built on [MNE-Python](https://mne.tools) and [MNE-BIDS](https://mne.tools/mne-bids/).

> **End users:** start with the **[User Guide](USER_GUIDE.md)** — it walks through installation, data layout, configuration, running the pipeline, reading outputs, the E-field step, performance tips, and troubleshooting.

## Scope (v1)

- Single-subject analyses.
- Ingests BIDS-formatted iEEG (EDF raw, pre-localized `electrodes.tsv`, `events.tsv`).
- Modular components that can be run independently per analysis:
  - Preprocessing (filtering, bad-channel detection, bipolar re-referencing)
  - Event parsing and epoching
  - Anatomical mapping of contacts to ROIs
  - Spectral power (PSD via multitaper / Welch)
  - Time-frequency (Morlet / multitaper TFR)
  - Phase analyses (envelope extraction, ITC, PLV-to-envelope, cross-frequency coupling)
  - Connectivity (coherence, wPLI, PLV matrices)
  - Cluster-permutation statistics
  - HTML per-subject report

Future (v2): multi-subject group statistics, TI E-field modeling integration (SimNIBS / ROAST).

## Experimental paradigm this pipeline assumes

Each subject has **two recordings** (one per stim block), each with:
- ~30 min baseline (pre-stim)
- Stim-test, active-stim, and no-stim periods (marked in `events.tsv`)

Stim parameters:
- **Block 1 (inhibition):** 2 kHz carriers, **130 Hz envelope** (gamma-range)
- **Block 2 (excitation):** 2 kHz carriers, **5 Hz envelope** (theta-range)

Carrier frequencies and envelope are configured per-subject via YAML (`configs/subject_XX.yaml`).

## Installation

Requires Python ≥ 3.10 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline.git
cd TI_SEEG_Analysis_Pipeline
uv sync --all-extras
```

Activate the environment: `source .venv/bin/activate` (or use `uv run ...`).

## Expected BIDS layout

```
<bids_root>/
├── dataset_description.json
├── participants.tsv
└── sub-XX/
    └── ses-YY/
        └── ieeg/
            ├── sub-XX_ses-YY_task-<task>_run-01_ieeg.edf
            ├── sub-XX_ses-YY_task-<task>_run-01_ieeg.json
            ├── sub-XX_ses-YY_task-<task>_run-01_channels.tsv
            ├── sub-XX_ses-YY_task-<task>_run-01_events.tsv
            ├── sub-XX_ses-YY_space-<space>_electrodes.tsv   # with anat labels
            └── sub-XX_ses-YY_space-<space>_coordsystem.json
```

`electrodes.tsv` is expected to have an anatomical-label column (e.g., from FreeSurfer `aparc+aseg`).

## Usage

All pipeline actions are driven by a YAML config. Start from the template:

```bash
cp configs/subject_template.yaml configs/subject_001_block1.yaml
# edit subject, session, bids_root, ti.f1_hz, ti.f2_hz, ti.envelope_hz, rois, ...
```

Run the full pipeline:

```bash
uv run ti-seeg run --config configs/subject_001_block1.yaml
```

Or run a single module:

```bash
uv run ti-seeg run --config configs/subject_001_block1.yaml --steps preprocessing,spectral
uv run ti-seeg run --config configs/subject_001_block1.yaml --steps tfr,phase
uv run ti-seeg run --config configs/subject_001_block1.yaml --steps connectivity,report
```

Available steps: `preprocessing`, `anatomy`, `spectral`, `tfr`, `phase`, `cfc`, `connectivity`, `stats`, `report`.

## Outputs

Written under `<derivatives_root>/sub-XX/ses-YY/<task>_run-<run>/`:

```
├── preprocessed_raw.fif
├── bad_channels.json
├── epochs/                    # per-condition Epochs
├── spectral/                  # PSD tables + figures
├── tfr/                       # AverageTFR .h5 + figures
├── phase/                     # envelope, ITC, PLV results
├── connectivity/              # connectivity matrices
├── stats/                     # cluster test results
├── figures/                   # standalone plots
├── report.html                # mne.Report assembly
└── run_manifest.json          # config snapshot, versions, timestamps
```

## Development

```bash
uv sync --all-extras --extra dev
uv run pre-commit install
uv run pytest
uv run ruff check
uv run mypy src/
```

## License

MIT — see [LICENSE](LICENSE).
