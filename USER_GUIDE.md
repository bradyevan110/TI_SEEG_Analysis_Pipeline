# TI_SEEG_Analysis_Pipeline — User Guide

A hands-on guide for researchers and clinicians using this pipeline to
analyze SEEG data recorded during temporal-interference (TI) stimulation
experiments.

> **Audience.** You have a BIDS-formatted SEEG dataset and you want to
> characterize how a TI stim block affected neural activity at each
> contact. You are not necessarily a Python developer — this guide
> sticks to the CLI surface and assumes basic command-line comfort.
>
> **Companion docs.**
> - [`README.md`](README.md) — one-page overview + quick-start.
> - [`HANDOFF.md`](HANDOFF.md) — current project state for developers.
> - [`HANDOFF_EFIELD.md`](HANDOFF_EFIELD.md) — internals of the E-field
>   modeling step (subprocess shell-out to SimNIBS, config knobs, etc.).

---

## Table of contents

1. [What this pipeline does](#1-what-this-pipeline-does)
2. [Installation](#2-installation)
3. [Preparing your data](#3-preparing-your-data)
4. [Writing a subject config](#4-writing-a-subject-config)
5. [Running the pipeline](#5-running-the-pipeline)
6. [The pipeline steps, one by one](#6-the-pipeline-steps-one-by-one)
7. [Outputs: what you get and how to read it](#7-outputs-what-you-get-and-how-to-read-it)
8. [The E-field modeling step (opt-in)](#8-the-e-field-modeling-step-opt-in)
9. [Memory and performance tips](#9-memory-and-performance-tips)
10. [Common workflows / recipes](#10-common-workflows--recipes)
11. [Troubleshooting](#11-troubleshooting)
12. [FAQ](#12-faq)

---

## 1. What this pipeline does

Each subject is recorded over two blocks of TI stimulation. The pipeline
takes one recording (one block, one run) at a time and produces:

- A **preprocessed** copy of the raw signal (notch-filtered, bandpassed,
  bipolar-rereferenced, with bad channels marked).
- **Spectral power** and **time-frequency** decompositions per condition
  (`active_stim`, `no_stim`, `baseline`, …).
- **Phase entrainment** estimates — how strongly each contact's signal
  locks to the predicted TI envelope frequency (the f1 − f2 beat).
- **Cross-frequency coupling** (theta-phase ↔ gamma-amplitude by default).
- **Connectivity** matrices (coherence, weighted PLI, PLV) within and
  between ROIs.
- **Cluster-permutation statistics** contrasting conditions.
- *(Optional)* **TI E-field maps** from a SimNIBS forward model, plus
  per-contact predicted envelope amplitude.
- A single **`report.html`** that consolidates the figures for review.

The intended use case is **per-subject characterization**: did this
contact pick up entrainment? Where is the envelope predicted to be
strong? Which conditions differ in power?

Group-level statistics across subjects are out of scope for v1.

### Scientific context (one paragraph)

Temporal interference stimulation delivers two high-frequency carriers
(e.g. 2000 Hz and 2130 Hz) through scalp electrodes. The two fields
interfere in tissue to produce a low-frequency **envelope** at the
difference frequency (e.g. 130 Hz). The envelope, in theory, drives
neurons preferentially at the geometric overlap of the two fields,
allowing non-invasive deep stimulation. For SEEG, the envelope shows
up directly in the recorded signal at strong-field contacts; the
pipeline disentangles "this contact is near the stim hotspot" from
"this contact shows neural entrainment to the envelope" by combining
the empirical PLV measurement with surrogate statistics and (when
enabled) the modeled envelope amplitude per contact.

---

## 2. Installation

### 2.1 Prerequisites

- **Python ≥ 3.10**
- **[uv](https://docs.astral.sh/uv/)** package manager (install with
  `curl -LsSf https://astral.sh/uv/install.sh | sh`).
- ~2 GB free RAM for default config; **24 GB+** if you don't crop or
  downsample a long, dense recording (see §9).

### 2.2 Clone and install

```bash
git clone https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline.git
cd TI_SEEG_Analysis_Pipeline
uv sync --all-extras
```

`--all-extras` pulls in `notebooks`, `dev`, and `efield` (pyvista for
3D plots). For a leaner install:

```bash
uv sync                    # main deps only
uv sync --extra dev        # plus dev tools
uv sync --extra efield     # plus pyvista (for 3D E-field rendering)
```

Verify:

```bash
uv run ti-seeg --help
uv run ti-seeg steps          # list available pipeline steps
uv run pytest -q              # 38 pass, 1 skip is the expected baseline
```

### 2.3 Optional: SimNIBS (only for the E-field step)

SimNIBS is **not** on PyPI. If you plan to run the `efield` step:

1. Download the standalone installer from
   <https://simnibs.github.io/simnibs/build/html/installation/installation.html>.
2. Install to `~/Applications/SimNIBS-4.x/` (or any path you prefer).
3. The pipeline auto-discovers `~/Applications/SimNIBS-*` and
   `/Applications/SimNIBS-*`. If you installed elsewhere, set the
   `efield.simnibs_dir` config field (see §8).

You can run every other step without SimNIBS — the pipeline only invokes
it when `efield.enabled: true`.

---

## 3. Preparing your data

The pipeline reads **BIDS-formatted iEEG**. Concretely, for a subject
`EMOP0649` recorded in session `ieeg1`, the on-disk layout is:

```
<bids_root>/
├── dataset_description.json
├── participants.tsv
└── sub-EMOP0649/
    └── ses-ieeg1/
        └── ieeg/
            ├── sub-EMOP0649_ses-ieeg1_electrodes.tsv
            ├── sub-EMOP0649_ses-ieeg1_coordsystem.json
            ├── sub-EMOP0649_ses-ieeg1_task-amygdalati_acq-09_run-01_ieeg.edf
            ├── sub-EMOP0649_ses-ieeg1_task-amygdalati_acq-09_run-01_ieeg.json
            ├── sub-EMOP0649_ses-ieeg1_task-amygdalati_acq-09_run-01_channels.tsv
            └── sub-EMOP0649_ses-ieeg1_task-amygdalati_acq-09_run-01_events.tsv
            # plus run-02 equivalents for the second stim block
```

### 3.1 What `electrodes.tsv` must contain

| Column | Required? | Notes |
|---|---|---|
| `name` | yes | Matches `channels.tsv`'s `name` column. |
| `x`, `y`, `z` | strongly recommended | MRI coordinates in mm. Use `n/a` (literal) for unlocalized contacts; they are skipped from the E-field per-contact sampling. |
| Anatomical label | recommended | First match from `aparc+aseg`, `region`, `anat`, `anatomy`, `label`, `roi`. Used by the `anatomy` step. |

### 3.2 What `channels.tsv` must contain

Standard BIDS columns (`name`, `type`, `units`, …). **The `type` column
must correctly mark SEEG depth contacts as `SEEG`** — the pipeline does
a `raw.pick("seeg")` early, which silently drops any non-SEEG row. If
your file lists depth contacts as `iEEG` instead, BIDS-validate first.

### 3.3 What `events.tsv` must contain

Standard BIDS columns: `onset` (s), `duration` (s), `trial_type`. The
`trial_type` values are mapped to the pipeline's canonical conditions
(`baseline`, `stim_test`, `active_stim`, `no_stim`) via the
`events.label_map` config knob.

Default mapping (see `configs/analysis_defaults.yaml`):

```yaml
events:
  label_map:
    baseline: baseline
    rest: baseline
    stim_test: stim_test
    test_stim: stim_test
    active_stim: active_stim
    stim_on: active_stim
    no_stim: no_stim
    stim_off: no_stim
```

If your events file uses different labels, add them to `label_map` in
the per-subject config (§4).

### 3.4 Optional: anatomical MRI

For volumetric plots and the `efield` step you'll also need:

- A subject T1 NIfTI (`anatomy.t1_path` in the config).
- *Optionally* a T2 NIfTI (`anatomy.t2_path`) — SimNIBS `charm`
  segments more accurately when both are supplied.

These live wherever you have them; they don't need to be under the BIDS
root.

---

## 4. Writing a subject config

The pipeline is driven entirely by YAML. Per-subject configs inherit
from `configs/analysis_defaults.yaml`, so you only set what differs.

### 4.1 Start from the template

```bash
cp configs/subject_template.yaml configs/subject_EMOP0649_run01.yaml
```

### 4.2 Fields you must edit

```yaml
defaults_file: configs/analysis_defaults.yaml   # leave as-is unless you fork the defaults

subject: "EMOP0649"
session: "ieeg1"
task: "amygdalati"
run: "01"
acquisition: "09"                # only if your filenames have `acq-NN`

bids_root: /Users/you/Projects/SEEG/Subject_bids_root
derivatives_root: /Users/you/Projects/SEEG/Subject_bids_root/derivatives/ti_seeg
```

These five paths/IDs locate the raw data and pick the output directory.

```yaml
ti:
  block_label: inhibition        # "inhibition" (130 Hz env) or "excitation" (5 Hz env)
  f1_hz: 2000.0
  f2_hz: 2130.0
  envelope_hz: 130.0
```

Set `f1_hz`, `f2_hz`, and `envelope_hz` from the stim protocol. The
pipeline uses `f1`/`f2` for notch-filtering the carriers; it uses
`envelope_hz` as the reference frequency for PLV-to-envelope.

```yaml
rois:
  hippocampus: ["hippocampus", "hippo", "ca1", "ca2", "ca3", "dg", "subiculum"]
  amygdala: ["amygdala", "amy"]
  temporal_pole: ["temporal pole", "temporalpole", "tpole"]
```

ROI groups: pipeline-internal name → list of **case-insensitive
substrings** matched against your `electrodes.tsv` anatomical-label
column. Add or remove ROIs as needed. Substrings are intentionally
loose so spelling variants ("Hippo", "hippocampal CA1", etc.) all map
to the same canonical group.

### 4.3 Fields you may want to override

Anything in `configs/analysis_defaults.yaml` can be overridden in a
subject config. Common overrides:

```yaml
preprocessing:
  line_freq: 60.0              # 50.0 in EU
  crop: [0, 600]               # only analyze the first 600 s — see §9
  target_sfreq: 1024.0         # downsample to this after crop (null = keep native)
  notch_carriers: true         # set false if carriers > Nyquist after downsample

events:
  label_map:
    my_custom_baseline: baseline
    my_active_label: active_stim

phase:
  cfc:
    enabled: false             # skip cross-frequency coupling for this subject
```

### 4.4 Validate before running

```bash
uv run ti-seeg validate configs/subject_EMOP0649_run01.yaml
```

Prints:

```
Config OK: subject=EMOP0649 task=amygdalati run=01
TI: f1=2000.0, f2=2130.0, envelope=130.0
Derivatives dir: /…/derivatives/ti_seeg/sub-EMOP0649/ses-ieeg1/task-amygdalati_run-01
```

Any pydantic schema errors surface here, before the long-running
analyses start.

---

## 5. Running the pipeline

### 5.1 Full run

```bash
uv run ti-seeg run --config configs/subject_EMOP0649_run01.yaml
```

This executes every step in order: preprocessing → anatomy → spectral →
tfr → phase → cfc → connectivity → stats → report. (If you've enabled
the `efield` step in the config, it slots in after `anatomy`.)

Typical wall time on a modern laptop for a 10-minute downsampled
recording: **5–15 minutes** for the full default pipeline (the bulk is
TFR + permutation stats). The `efield` step alone takes **1–3 hours**
the first time it runs (segmentation), then minutes on cached runs.

### 5.2 Selective re-runs

`--steps` accepts any comma-separated subset of:

```
preprocessing, anatomy, efield, spectral, tfr, phase, cfc,
connectivity, stats, report
```

Examples:

```bash
# Just preprocess (writes preprocessed_raw.fif + bad_channels.json)
uv run ti-seeg run --config <cfg> --steps preprocessing

# Re-render the TFR section after tweaking baseline window
uv run ti-seeg run --config <cfg> --steps tfr,report

# Rebuild only the report from existing outputs
uv run ti-seeg run --config <cfg> --steps report
```

Most steps cache their inputs from disk if they're missing in memory.
For example, running `--steps spectral` without first running
`preprocessing` will work as long as `preprocessed_raw.fif` already
exists in the derivatives dir.

### 5.3 Run multiple subjects/blocks

The CLI handles one config at a time. To process several subjects/runs,
wrap the call in a shell loop:

```bash
for cfg in configs/subject_EMOP0649_run{01,02}.yaml \
          configs/subject_EMOP0701_run{01,02}.yaml; do
  uv run ti-seeg run --config "$cfg" || echo "FAILED: $cfg"
done
```

(Group statistics across subjects are not part of v1 — coming in v2.)

### 5.4 The per-step convenience scripts

`scripts/run_<step>.py` exposes each step as a one-shot CLI for the
steps that don't have a single dedicated entry. These are thin wrappers
around `ti-seeg run --steps <step>`; use them if you prefer:

```bash
uv run scripts/run_preprocessing.py --config configs/subject_EMOP0649_run01.yaml
uv run scripts/run_full_pipeline.py --config configs/subject_EMOP0649_run01.yaml
```

(There's no `run_efield.py` in v1 — use `ti-seeg run --steps efield`.)

---

## 6. The pipeline steps, one by one

### 6.1 `preprocessing`

What it does, in order:

1. Reads the BIDS recording (`mne_bids.read_raw_bids`), restricts to
   SEEG channels.
2. Optional **crop** to `preprocessing.crop = [tmin, tmax]`. Applied
   *before* `load_data`, so memory stays bounded.
3. Optional **resample** to `preprocessing.target_sfreq`.
4. **Notch filtering** at line frequency + harmonics (e.g. 60, 120, …,
   360 Hz). If `notch_carriers: true` and the carrier f1, f2 (and their
   harmonics) are below the Nyquist, those are notched too.
5. **Bandpass** at `preprocessing.bandpass = [hp, lp]`. `lp = null`
   means use 0.45 × sample rate.
6. **Bad channel detection** by variance + kurtosis Z-scores
   (configurable thresholds).
7. **Reference**: `bipolar` (within-shank adjacent pairs by default),
   `car` (common average), or `monopolar` (leave as-is).
8. Saves `preprocessed_raw.fif` and `bad_channels.json` to the
   derivatives directory.

Why bipolar by default: depth electrodes are spatially adjacent on each
shank, so bipolar pairing isolates focal sources and cancels common-mode
noise. The pairing logic parses shank prefixes (e.g. `LAH1`, `LAH2`)
and only pairs adjacent contacts on the same shank.

### 6.2 `anatomy`

Groups contacts into ROIs from `electrodes.tsv` anatomical labels.
Substring matches are case-insensitive (so "LeftHippocampus" matches the
`hippocampus` ROI). Writes an ROI counts table into `report.html` and
saves a contact-on-brain figure.

If `electrodes.tsv` has no anatomical-label column or no coordinates,
this step still runs but produces an empty / fallback figure.

### 6.3 `efield` (opt-in — see §8)

Runs SimNIBS to compute the predicted TI envelope amplitude per contact.
Disabled by default (`efield.enabled: false`). Adds 1–3 hours of wall
time on the first run.

### 6.4 `spectral`

For each condition (active_stim, no_stim, baseline, …):

1. Builds `mne.Epochs` from the events list, using the per-condition
   window in `events.epoch_window`.
2. Computes PSD per epoch via multitaper (default) or Welch.
3. Aggregates power into named bands (delta, theta, alpha, beta,
   low_gamma, high_gamma — see `spectral.bands`).
4. Writes `spectral/band_power.tsv` and one PSD plot per condition.

### 6.5 `tfr`

Time-frequency decomposition per condition:

1. Morlet wavelets (default) or multitaper.
2. Log freqs from `fmin` to `fmax` (default 2–200 Hz).
3. Per-epoch TFR is baseline-corrected against `tfr.baseline` (default:
   logratio against the −1.0 to −0.1 s pre-event window).
4. Saves `tfr/tfr_<condition>-tfr.h5` and per-ROI mean TFR plots.

### 6.6 `phase`

PLV-to-envelope analysis on `active_stim` epochs:

1. Bandpasses around `ti.envelope_hz` (width = `phase.envelope.bandwidth_hz`).
2. Extracts Hilbert phase.
3. Builds a reference envelope phase from the epoch-mean signal (works
   because the TI beat appears in intracranial recordings near the stim
   site).
4. Computes PLV between each channel's phase and the reference phase.
5. Generates surrogate distributions via time-shifting
   (`phase.entrainment.n_surrogates`, default 200).
6. Writes `phase/plv_to_envelope.tsv` with PLV, surrogate-derived p, and
   z-scores per channel.

Skipped (with a warning) if no `active_stim` epochs are found.

### 6.7 `cfc`

Cross-frequency coupling (Tort 2010 modulation index) per condition:

1. Filters into a phase band (default theta 4–8 Hz) and one or more
   amplitude bands (default low gamma 30–80, high gamma 80–150).
2. Computes Tort MI per channel × amp band.
3. Writes `phase/cfc_mi_<condition>.tsv`.

Can be disabled per-subject with `phase.cfc.enabled: false`.

### 6.8 `connectivity`

For each condition × frequency band × method, computes a channel ×
channel connectivity matrix:

- Methods: coherence (`coh`), weighted PLI (`wpli`), PLV (`plv`).
- Bands: configurable (default theta + low_gamma + high_gamma).
- Writes `connectivity/con_<method>_<band>_<condition>.npz` + a heatmap
  per matrix.

### 6.9 `stats`

Light-touch cluster-permutation contrast on TFR data — by default
compares `active_stim` vs `no_stim` on the first data channel using
`mne.stats.permutation_cluster_test`. Outputs go to the log and a stats
table; full per-channel implementation is a v2 follow-up.

### 6.10 `report`

Builds the consolidated `report.html` from every figure other steps have
added to the `ReportBuilder`. Always runs last unless you've passed
`--steps` without `report`.

---

## 7. Outputs: what you get and how to read it

Default derivatives layout:

```
<derivatives_root>/sub-<id>/ses-<sess>/task-<task>_run-<run>/
├── preprocessed_raw.fif              # full filtered + referenced recording
├── bad_channels.json                 # which channels were flagged + why
├── spectral/
│   └── band_power.tsv                # long-form: channel × condition × band
├── tfr/
│   └── tfr_<condition>-tfr.h5        # mne.AverageTFR
├── phase/
│   ├── plv_to_envelope.tsv           # channel, plv, p_value, z
│   └── cfc_mi_<condition>.tsv        # channel × amp_band MI matrix
├── connectivity/
│   └── con_<method>_<band>_<cond>.npz
├── figures/
│   └── <section>_<title>.png         # the PNGs embedded in report.html
├── efield/                           # only if the efield step ran
│   ├── m2m_<subject>/                # SimNIBS segmentation outputs (cached)
│   ├── pair_a/, pair_b/              # per-pair FEM outputs
│   ├── ti_envelope.{msh,nii.gz}      # combined envelope
│   ├── ti_envelope_surface.npz       # portable surface for 3D viz
│   └── ti_per_contact.tsv            # name, envelope_mean, envelope_max, n_voxels
├── config_snapshot.yaml              # exactly what config produced these outputs
├── pipeline.log                      # full INFO-level log
├── run_manifest.json                 # versions + timestamps + per-step status
└── report.html                       # open this in a browser
```

### 7.1 How to interpret `plv_to_envelope.tsv`

Three columns:

- **`plv`** — phase locking value, in [0, 1]. 0 = uncorrelated, 1 =
  perfectly locked. Values >~0.2 on real data usually mean *something*
  is locking; whether it's neural entrainment vs passive envelope
  pickup needs the surrogate test.
- **`p_value`** — fraction of the surrogate distribution that exceeded
  the measured PLV. Smaller = more significant.
- **`z`** — number of surrogate-SDs the measured PLV sits above the
  surrogate mean.

**Important caveat.** Contacts near the stim site will show high PLV
*even without neural entrainment* because the envelope appears in the
recorded signal directly (rectification at the electrode–tissue
interface). To separate "field is strong here" from "neurons are
following the envelope," compare the per-contact PLV against the
**modeled envelope amplitude** from the `efield` step (§8): a contact
with high PLV but *low* predicted field is a stronger candidate for
real entrainment than one with high PLV in a high-field region.

### 7.2 How to interpret `cfc_mi_<condition>.tsv`

Rows = channels, columns = amplitude bands (e.g. `30-80Hz`,
`80-150Hz`). Values = Tort modulation index — typically 0.001–0.01 on
clean data; values >0.02 are noteworthy. The MI is a histogram-based
measure, so very short recordings or sparse events undercount.

### 7.3 How to interpret connectivity matrices

Stored as `.npz` with two keys: `matrix` (n_chan × n_chan) and
`ch_names` (the order). Read in Python:

```python
import numpy as np
arr = np.load("connectivity/con_wpli_theta_active_stim.npz", allow_pickle=True)
mat = arr["matrix"]            # (n_chan, n_chan), values in [0, 1] or [-1, 1]
names = arr["ch_names"]
```

For wPLI and coherence the values are in [0, 1]; PLV is also in [0, 1].
Diagonal is typically zero (or ignored).

---

## 8. The E-field modeling step (opt-in)

The `efield` step computes a 3D map of the predicted TI envelope inside
the head, then samples it at each SEEG contact. See `HANDOFF_EFIELD.md`
for full internals.

### 8.1 Prereqs

- A working SimNIBS install (see §2.3).
- The subject's T1 (and ideally T2) MRI on disk.
- The stim-electrode names / coordinates (the *scalp* electrodes that
  delivered the carriers — these are *not* the recording SEEG contacts).

### 8.2 First-time setup per subject

```yaml
anatomy:
  t1_path: /path/to/sub-EMOP0649_T1w.nii.gz
  t2_path: /path/to/sub-EMOP0649_T2w.nii.gz   # optional, recommended

efield:
  enabled: true
  montage:
    pair_a:
      anode:   { name: "F4", radius_mm: 12.0 }   # 10-20 name OR position: [x, y, z] mm
      cathode: { name: "P4", radius_mm: 12.0 }
      current_mA: 1.0
      label: "carrier_2000Hz"
    pair_b:
      anode:   { name: "F8", radius_mm: 12.0 }
      cathode: { name: "P8", radius_mm: 12.0 }
      current_mA: 1.0
      label: "carrier_2130Hz"
  contact_sampling_radius_mm: 2.0
  visualize_3d: true            # set false to skip the pyvista 3D plot
```

Pad radius and current default to SimNIBS tDCS defaults (12 mm circular
pad, 1 mA). Adjust to match your protocol.

### 8.3 What happens when you run it

```bash
uv run ti-seeg run --config <cfg> --steps efield,report
```

First-time run:

1. Auto-discovers SimNIBS at `~/Applications/SimNIBS-*` (or uses
   `efield.simnibs_dir` if set).
2. Runs `charm` to segment the T1[+T2] into a head model — **1–3 hours**
   the first time, cached thereafter.
3. Runs two FEM solves (one per carrier pair) — **5–10 minutes each**.
4. Combines them via `simnibs.utils.TI.get_maxTI` (the Grossman 2017
   max-modulation envelope formula).
5. Samples the volumetric envelope at every contact in `electrodes.tsv`
   inside a sphere of `contact_sampling_radius_mm` (default 2 mm).
6. Renders three figures into `report.html`: orthogonal slices, 3D
   surface (if pyvista installed), per-contact bar chart sorted by
   predicted envelope amplitude.

Subsequent runs reuse the cached `m2m_<subject>/` segmentation and the
per-pair FEM outputs; total time drops to minutes.

### 8.4 Running without a subject MRI (template fallback)

If `anatomy.t1_path` is null, the pipeline falls back to a precomputed
template head model:

```yaml
efield:
  fallback_to_template: true
  template_m2m_dir: /path/to/m2m_ernie   # required when fallback is used
```

The template head is **not your subject's anatomy** — per-contact
amplitudes are approximate. The pipeline emits a loud warning so this
isn't accidental.

### 8.5 Re-running with a different montage

The cached charm output (`m2m_<subject>/`) is reused. Only the per-pair
FEM solves are redone (in `pair_a/`, `pair_b/`). To force a full
re-run:

```yaml
efield:
  force_resegment: true
```

This also re-runs charm. To clear only the FEM cache, delete the
`pair_a/`, `pair_b/`, and `ti_envelope.*` files manually.

---

## 9. Memory and performance tips

### 9.1 The 90-minute × 2 kHz × 277-channel trap

A full uncropped recording at 2 kHz with hundreds of channels can be
**~24 GB** in memory. On a 16 GB laptop, just loading the raw file
will OOM-kill the process.

Two config knobs handle this:

```yaml
preprocessing:
  crop: [0, 600]            # work with the first 10 minutes
  target_sfreq: 1024.0      # downsample after crop (preserves >500 Hz signal)
```

`crop` is applied *before* `load_data`, so unused samples never enter
memory. `target_sfreq` halves the working set further. Combined, a
10-minute downsampled slice of a 277-channel recording is **<2 GB** —
comfortably analyzable on a laptop.

Caveat: if you downsample to e.g. 1024 Hz, the carrier frequencies
(2000 Hz) are above Nyquist (512 Hz). Set
`preprocessing.notch_carriers: false` — there is nothing to notch in a
sub-Nyquist signal anyway.

### 9.2 Cache aware

Each long-running step writes its outputs to disk and skips re-running
when those outputs already exist. The big ones:

| Step | Cache file | What forces a redo |
|---|---|---|
| `preprocessing` | `preprocessed_raw.fif` | Manually delete or change preprocessing config and rerun |
| `efield` charm | `efield/m2m_<sub>/<sub>.msh` | `efield.force_resegment: true` |
| `efield` FEM | `efield/pair_<a\|b>/<sub>_TDCS_1_scalar.msh` | `force_resegment` *or* manually delete the pair dir |

Other steps are fast enough that they always recompute.

### 9.3 Parallel runs

The pipeline itself is single-process. To run multiple subjects in
parallel, kick off separate shells:

```bash
uv run ti-seeg run --config configs/subject_001.yaml &
uv run ti-seeg run --config configs/subject_002.yaml &
wait
```

The TFR step uses `joblib` internally and will saturate available cores
already, so for a single subject this won't speed things up much. For
multi-subject batches, parallelism helps proportionally.

---

## 10. Common workflows / recipes

### 10.1 "I changed the carrier frequencies — redo just the parts that depend on them"

```bash
# Notch + bandpass change → re-preprocess and everything downstream
uv run ti-seeg run --config <cfg> --steps preprocessing,spectral,tfr,phase,cfc,connectivity,stats,report
```

### 10.2 "I tweaked the ROI list — only redo anatomy + the report"

ROI grouping affects which channels get aggregated in TFR plots and
connectivity views. Re-run:

```bash
uv run ti-seeg run --config <cfg> --steps anatomy,tfr,connectivity,report
```

(Spectral and phase aren't ROI-aware, so they don't need redoing.)

### 10.3 "I have two recordings per subject — what do I run?"

Create one config per run and run them sequentially:

```bash
cp configs/subject_template.yaml configs/subject_EMOP0649_run01.yaml
cp configs/subject_template.yaml configs/subject_EMOP0649_run02.yaml
# edit each to set run, ti.envelope_hz, etc.
uv run ti-seeg run --config configs/subject_EMOP0649_run01.yaml
uv run ti-seeg run --config configs/subject_EMOP0649_run02.yaml
```

Outputs land in separate `task-*_run-01/` and `task-*_run-02/`
directories under the derivatives root.

### 10.4 "I want to test the pipeline before running on a real subject"

A synthetic-data test suite ships with the repo:

```bash
uv run pytest -q
```

This exercises every step against synthesized SEEG data with a known
envelope-modulated carrier on one channel. Expected: **38 pass, 1
skipped** (the 3D pyvista test is skipped on the headless CI runner and
when pyvista isn't installed).

### 10.5 "I'm iterating on the E-field montage — how do I avoid redoing charm?"

charm runs once and caches under `efield/m2m_<subject>/`. As long as
you don't touch `anatomy.t1_path` or set `force_resegment: true`,
montage tweaks only redo the two FEM solves (~10–20 minutes each).

If you want to swap stim electrodes entirely, manually clear the
per-pair caches:

```bash
rm -rf <derivatives>/efield/pair_a <derivatives>/efield/pair_b \
       <derivatives>/efield/ti_envelope.*
```

Then rerun `--steps efield,report`.

### 10.6 "I only want to look at the report"

After at least one successful run:

```bash
open <derivatives>/sub-<id>/.../report.html
```

To regenerate the report from existing per-step outputs (e.g. after
manually editing a figure):

```bash
uv run ti-seeg run --config <cfg> --steps report
```

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ValidationError: Field required` from pydantic | A required field is missing in your subject YAML (`subject`, `task`, `bids_root`, `ti.f1_hz`, `ti.f2_hz`, `ti.envelope_hz`) | Run `uv run ti-seeg validate <cfg>`; add the missing field. |
| `BIDSPath not found` | Your filenames don't match BIDS naming conventions, or `acquisition` / `session` is unset in the config but present in filenames | Match the config to the filename: if files have `acq-09`, set `acquisition: "09"` in the config. |
| OOM killed during `preprocessing` | Recording too big for available RAM | Set `preprocessing.crop` and/or `preprocessing.target_sfreq`. See §9.1. |
| `filter_length (54069) is longer than the signal` warning | Your crop window is shorter than the notch filter length | Either crop a longer window (>30 s) or accept the warning — it doesn't fail. |
| "No active_stim epochs; skipping phase entrainment step" | Your `events.tsv` `trial_type` doesn't map to `active_stim` via `events.label_map` | Add your label to `label_map` in the subject config. |
| `compute_ti_field` is no longer defined | You're on a downstream branch / old import | `ti_seeg.source.efield` is the new module; see `HANDOFF_EFIELD.md`. |
| `FileNotFoundError: Could not locate a SimNIBS install` | The `efield` step can't find SimNIBS | Set `efield.simnibs_dir: /path/to/SimNIBS-4.x` or `export SIMNIBSDIR=…`. |
| `RuntimeError: charm did not produce …<sub>.msh` | SimNIBS segmentation crashed | Inspect `m2m_<sub>/charm_log.html`; usually a bad MRI orientation. Try a fresh T1, or pass `efield.force_resegment: true`. |
| Empty / black 3D E-field plot | Grey-matter mesh tag changed in your SimNIBS version | See `HANDOFF_EFIELD.md` §10 troubleshooting. |
| `ImportError: pyvista is required for 3D E-field plots` | The `efield` optional dep isn't installed | `uv sync --extra efield`. |
| Tests segfault on Linux during `test_plot_efield_3d_mesh_or_skip` | Headless VTK can't grab an OpenGL context | Wrap pytest in `xvfb-run pytest`, or just let the test skip — the rest of the suite is independent. |

### Diagnostic commands

```bash
# Confirm config parses + see resolved derivatives path
uv run ti-seeg validate <cfg>

# Print the available pipeline steps
uv run ti-seeg steps

# See exactly what ran for a previous invocation
cat <derivatives>/.../run_manifest.json | jq .

# Inspect the log for an existing run
less <derivatives>/.../pipeline.log
```

---

## 12. FAQ

**Q: My events.tsv has labels in another language / convention. Do I need to rename them in the TSV?**
No — add the mapping to `events.label_map` in your subject config.
Original TSVs stay untouched.

**Q: I don't have anatomical labels in `electrodes.tsv`. What breaks?**
The `anatomy` step still runs but produces an empty ROI grouping (no
hippocampus / amygdala / etc. partitions). TFR plots fall back to
flat-channel views. PLV, CFC, spectral, and connectivity are all
unaffected — they don't depend on anatomy.

**Q: Can I run this on macOS / Linux / Windows?**
macOS and Linux are routinely exercised. Windows isn't tested. The
shell-out to SimNIBS in the `efield` step uses POSIX-style paths in
`subprocess.run` calls — should work but YMMV on Windows. Open an
issue with details if you hit something.

**Q: Where does the pipeline keep its cache?**
Inside the derivatives directory (`<derivatives_root>/sub-<id>/…/`).
Delete a subdirectory to invalidate that step's cache; the next run
recomputes it.

**Q: Can I disable a step entirely?**
For most steps, yes — each one has an `.enabled: false` knob (e.g.
`phase.cfc.enabled`, `spectral.enabled`, `report.enabled`,
`stats.enabled`). The `efield` step is disabled by default and only
runs when you set `efield.enabled: true`. The `preprocessing` and
`anatomy` steps don't have enable flags — they're prereqs for
everything else.

**Q: I want to share the report with a collaborator who doesn't have the data.**
`report.html` is self-contained — open it in any browser, or just zip
the whole `task-*_run-*/` directory.

**Q: How do I cite the pipeline?**
There isn't a paper yet. For methodological choices, cite the
underlying algorithms:
- TI envelope formula: Grossman et al. (2017) *Cell* 169(6):1029–1041.
- Tort modulation index: Tort et al. (2010) *J Neurophysiol* 104(2):1195–1210.
- MNE-Python / MNE-BIDS for everything in the preprocessing /
  spectral / TFR / phase / connectivity layers.

**Q: I think I found a bug.**
Open an issue at
<https://github.com/bradyevan110/TI_SEEG_Analysis_Pipeline/issues>
with: the exact command you ran, the relevant slice of `pipeline.log`,
your subject config (with paths redacted), and the SimNIBS version if
the `efield` step is involved.

---

*Last updated: 2026-05-12.*
