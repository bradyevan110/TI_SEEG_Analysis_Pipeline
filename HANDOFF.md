# TI_SEEG_Analysis_Pipeline — Handoff document

> **Purpose of this file:** self-contained briefing so a fresh Claude instance
> (or human collaborator) can pick up the project on a different machine
> without prior conversation history. The previous handoff (v1, dated
> 2026-04-24) is preserved in git history at commit `a5e8e8d`.
>
> **Last updated:** 2026-05-04 (v2)

---

## 0. TL;DR for the next instance

- Pipeline scaffold + tests are intact; **all 25 unit tests pass**.
- The original §6 numerical-instability bug in `bandpass_hilbert` is **fixed** (SOS form). A latent issue in the entrainment surrogate test it exposed is also fixed.
- BIDS layout for subject **EMOP0649** at `/Users/ebrady/Projects/SEEG Processing/` has been prepared (BIDS-strict folder structure, retyped `channels.tsv`, synthesized `electrodes.tsv`, minimal `coordsystem.json`, cleaned `events.tsv`). Two runs: `run-01` (130 Hz envelope) and `run-02` (5 Hz envelope), both `task-amygdalati`, `acq-09`.
- New config knobs: `preprocessing.notch_carriers`, `preprocessing.crop`, `preprocessing.target_sfreq`, plus a top-level `acquisition` entity.
- **Outstanding:** the dry run was OOM-killed loading the full 90-min × 2048 Hz × 277-channel EDF (~24 GB). Subject YAMLs have been written with `crop: [0, 600]` and a target_sfreq downsample to bring the working set to <2 GB. The user wants the next session run on a more powerful machine; cropping/downsampling may be removed if RAM allows.

---

## 1. What changed since the v1 handoff

Three commits, all on `main`:

| Commit | What |
|---|---|
| `6de3674` | Switch `bandpass_hilbert` to second-order-sections form (`sosfiltfilt`); fix the entrainment surrogate test that the buggy filter was masking; ruff format pass on the tree (14 files reformatted). |
| `7bc354b` | Add `preprocessing.notch_carriers: bool` (default `true`) so subjects with above-Nyquist carriers can disable carrier notching. |
| `ea39260` | After `read_raw_bids`, `raw.pick("seeg")` so non-depth channels (scalp 10-20, EKG, DC, OSAT, Pleth, TRIG) don't pollute bipolar pairing. Relies on `channels.tsv` types being correct. |
| `6fb6678` | Add `preprocessing.crop` (applied **before** `load_data` to limit memory) and `preprocessing.target_sfreq` (applied after pick). Add top-level `acquisition` entity for BIDS files with `acq-NN` tokens. |

Tests after each commit: 25/25 passing.

---

## 2. Subject EMOP0649 — current data state

Subject directory: `/Users/ebrady/Projects/SEEG Processing/sub-EMOP0649/ses-ieeg1/ieeg/`

What's there now (all done, no further data prep needed unless the data moves to a new machine):

```
/Users/ebrady/Projects/SEEG Processing/
├── dataset_description.json                 # NEW — minimal, BIDSVersion 1.8.0
└── sub-EMOP0649/
    └── ses-ieeg1/
        └── ieeg/                            # NEW subdirectory; files moved here
            ├── sub-EMOP0649_ses-ieeg1_electrodes.tsv     # NEW — 236 SEEG rows
            ├── sub-EMOP0649_ses-ieeg1_coordsystem.json   # NEW — minimal "Other"
            ├── sub-EMOP0649_..._run-01_ieeg.{edf,json}
            ├── sub-EMOP0649_..._run-01_channels.tsv      # MODIFIED — retyped
            ├── sub-EMOP0649_..._run-01_events.tsv        # MODIFIED — durations clamped
            └── (run-02 equivalents)
```

### What was done to the BIDS data

1. **Wrote `dataset_description.json`** at the BIDS root.
2. **Created `ieeg/`** modality subfolder under `sub-EMOP0649/ses-ieeg1/` and moved the loose files into it (mne-bids requires this layout).
3. **Re-typed `channels.tsv`** for both runs:
   - 19 scalp 10-20 channels (`Fp1/2, F3/4/7/8/z, C3/4/z, P3/4/7/8/z, O1/2, T7/8`) → type `EEG` (was `SEEG`)
   - `EKG` → `ECG`
   - 16 `DC*` channels + `OSAT` + `Pleth` + `Patient Event` → `MISC`
   - `TRIG` → `TRIG`
   - 236 depth contacts kept as `SEEG`
   - One `EDF Annotations` row that didn't correspond to a real EDF channel was dropped (channel-count mismatch fix).
4. **Cleaned `events.tsv`** for both runs: clamped 23 negative `duration` values (sentinel `-1.0`) to `0.0`. mne-bids' `set_annotations` asserts `duration >= 0`.
5. **Synthesized `electrodes.tsv`** with 236 rows (one per SEEG depth contact). Coordinates are all `n/a`; `anat` is filled from the shank-prefix mapping (see §3). One file covers both runs.
6. **Minimal `coordsystem.json`** so mne-bids accepts the electrodes.tsv (it requires the pair if either is present). `iEEGCoordinateSystem: "Other"`, units `n/a`.

### The shank-prefix → anatomy mapping in `electrodes.tsv`

Cross-checked against the surgical implant list and the amplifier montage sheet (both in `sub-EMOP0649/`):

| Shank | Contacts (chs.tsv) | Anatomical label |
|---|---|---|
| RAm | 16 | Right-Amygdala |
| LAm | 18 | Left-Amygdala |
| RAHc / LAHc | 15 / 15 | Right-/Left-Hippocampus-Anterior |
| RMiHc / LMiHc | 15 / 15 | Right-/Left-Hippocampus-Middle |
| RPHc | 15 | Right-Hippocampus-Posterior |
| REc | 13 | Right-Entorhinal |
| RPHG / RPPHG | 13 / 14 | Right-(Posterior)ParaHippocampalGyrus |
| RTePo | 18 | Right-TemporalPole |
| ROFc | 18 | Right-OrbitoFrontalCortex |
| RAIn | 15 | Right-AnteriorInsula |
| RANT | 18 | Right-AnteriorNucleusThalamus |
| RPUL | 18 | Right-Pulvinar |
| **Total** | **236** | |

Limitation: shank-prefix-as-ROI is coarse — every contact on a given shank is given the same target-anatomy label. True per-contact localization would require post-op CT/MRI fusion + atlas (FreeSurfer aparc+aseg or similar). The user does not currently have that output. Refining the labels later is a drop-in `electrodes.tsv` swap; no code changes needed.

---

## 3. Subject configs (gitignored — recreate locally if missing)

`configs/subject_*.yaml` is gitignored by design. The two configs in use locally are below; recreate them under `configs/` on the new machine.

### `configs/subject_EMOP0649_run01.yaml`

```yaml
defaults_file: analysis_defaults.yaml

subject: "EMOP0649"
session: "ieeg1"
task: "amygdalati"
acquisition: "09"
run: "01"

bids_root: /Users/ebrady/Projects/SEEG Processing
derivatives_root: /Users/ebrady/Projects/SEEG Processing/derivatives/ti_seeg

ti:
  block_label: inhibition
  f1_hz: 2000.0
  f2_hz: 2130.0
  envelope_hz: 130.0

preprocessing:
  notch_carriers: false        # carriers above Nyquist (sfreq=2048, carriers ~2 kHz)
  crop: [0.0, 600.0]           # first 10 minutes only — REMOVE on a beefy machine
  target_sfreq: 1024.0         # half native — REMOVE/raise on a beefy machine

events:
  label_map:
    "task start": baseline
    "stim start": active_stim
    "stim stop": no_stim
    "start of TI calibration": stim_test

phase:
  cfc:
    phase_band: [4.0, 8.0]
    amp_bands:
      - [80.0, 200.0]
      - [200.0, 400.0]

rois:
  amygdala: ["amygdala"]
  hippocampus: ["hippocampus", "hippo"]
  entorhinal: ["entorhinal"]
  parahippocampal: ["parahippocampal"]
  temporal_pole: ["temporalpole"]
  orbitofrontal: ["orbitofrontal"]
  insula: ["insula"]
  thalamus_ant: ["anteriornucleusthalamus"]
  pulvinar: ["pulvinar"]
```

### `configs/subject_EMOP0649_run02.yaml`

Same as run-01 except:

```yaml
run: "02"

ti:
  block_label: excitation
  f1_hz: 2000.0
  f2_hz: 2005.0
  envelope_hz: 5.0

preprocessing:
  notch_carriers: false
  crop: [0.0, 600.0]
  target_sfreq: 512.0          # 5 Hz envelope; aggressive downsample is fine

events:
  label_map:
    "start baseline": baseline
    "stim start": active_stim
    "stim stop": no_stim

phase:
  envelope:
    bandwidth_hz: 1.0
  cfc:
    phase_band: [3.0, 7.0]
    amp_bands:
      - [30.0, 80.0]
      - [80.0, 150.0]

# rois: same as run-01
```

---

## 4. The dry run that hasn't completed

### What's been attempted

```bash
uv run ti-seeg run --config configs/subject_EMOP0649_run01.yaml \
  --steps preprocessing,anatomy,spectral
```

First attempt (no crop, full 90 min): got past metadata read, started the EDF binary load (`Reading 0 ... 11061055 = 0.000 ... 5400.906 secs...`), then was killed — almost certainly OOM. Memory math: 5400s × 2048 Hz × 277 ch × 8 bytes ≈ 24 GB.

Subject configs now have `crop: [0, 600]` + `target_sfreq` to bring this to <2 GB. Has not been re-run after that change.

### What to try first on the new machine

1. **Verify BIDS load works.** Smoke test:
   ```bash
   uv run python -c "
   from ti_seeg.config import load_config
   from ti_seeg.io import load_subject
   cfg = load_config('configs/subject_EMOP0649_run01.yaml')
   sub = load_subject(cfg)
   print('raw:', sub.raw)
   print('events:', len(sub.events), 'rows; canonical:', sorted(set(sub.events['canonical'].dropna())))
   print('electrodes:', len(sub.electrodes))
   "
   ```
2. **Run the cheap subset:**
   ```bash
   uv run ti-seeg run --config configs/subject_EMOP0649_run01.yaml \
     --steps preprocessing,anatomy,spectral
   ```
   Inspect outputs under `/Users/ebrady/Projects/SEEG Processing/derivatives/ti_seeg/sub-EMOP0649/ses-ieeg1/task-amygdalati_run-01/`:
   - `preprocessed_raw.fif` — the cleaned bipolar-rereferenced raw
   - `bad_channels.json`
   - `spectral/band_power.tsv`
   - `report.html` (qc + anatomy + spectral sections)
3. **If the report looks sane**, expand to the full pipeline:
   ```bash
   uv run ti-seeg run --config configs/subject_EMOP0649_run01.yaml \
     --steps preprocessing,anatomy,spectral,tfr,phase,cfc,connectivity,stats,report
   ```
4. **Then run-02.** Same cycle.
5. **On a beefy machine**, drop `crop` (set to `[null, null]`) and raise `target_sfreq` (or set to `null` for native rate).

### Expected report content for the dry run to be considered "passing"

- Carrier frequencies are *not* in PSD (they're above Nyquist anyway with this sfreq).
- Baseline PSD shape is roughly 1/f.
- During `active_stim`, run-01 should show a sharp 130 Hz peak; run-02 should show a sharp 5 Hz peak. Either of these can be passive (volume conduction of the stim envelope through tissue) or response-driven — distinguishing requires PLV-to-envelope + surrogates (the `phase` step).
- ROI grouping populates 15 groups with non-zero counts.
- No crashes across conditions.

---

## 5. Known gotchas

1. **Carriers above Nyquist.** This subject's recording sfreq is 2048 Hz (Nyquist = 1024 Hz); TI carriers are at ~2000 / 2130 Hz, so they cannot be present in the digitized signal — they were anti-alias filtered in hardware. `preprocessing.notch_carriers: false` reflects this. Subjects with sfreq ≥ 4× max carrier should leave it `true`.
2. **Stim-envelope artifact in band of interest.** When TI is on, the **envelope** itself shows up directly (tissue rectification) at the frequency we want to study (130 Hz / 5 Hz). The pipeline uses this artifact as a phase reference (`extract_ti_envelope`, `plv_to_reference_with_surrogates`) — that's a feature, not a bug. Off-envelope-band power (e.g., gamma during 5 Hz stim) is the cleanest place to look for stim-driven response unrelated to direct artifact. Template-subtraction / SSP / ML denoising are v2 candidates if the surrogate-based approach proves insufficient.
3. **`channels.tsv` types matter.** The loader does `raw.pick("seeg")`. If a future subject's `channels.tsv` mistypes channels, they'll silently disappear. Inspect `bids.electrodes` row count vs `raw.ch_names` count after load.
4. **Bipolar pairing parses shank by regex** `^([A-Za-z'`]+)\s*-?\s*0*([0-9]+)$`. Anything that fits `<letters><digits>` and has consecutive numbers will be paired. Scalp channels (`F3, F4`) would pair across hemispheres — `pick("seeg")` is what saves us.
5. **`events.tsv` durations.** mne asserts non-negative. If a future subject has `-1.0` sentinels (this one did), they need to be clamped to `0` before load.
6. **Surrogate test brittleness.** `test_surrogate_distinguishes_driven_from_noise` was previously passing because of the buggy filter randomizing phases. With the fixed filter, the test required adding noise to the *reference* (not just the channel) so time-shift surrogates produce a non-degenerate null. Look at this if surrogate p-values look weird on real data.

---

## 6. Outstanding work after the dry run completes

Tracked as GitHub issues in `bradyevan110/TI_SEEG_Analysis_Pipeline`:

1. Get a clean v1 dry run — both runs, all steps, plausible report.html.
2. Replace shank-prefix anatomy with per-contact labels (post-op CT/MRI + atlas).
3. Polish HTML report: section grouping, narrative text, collapsible config snapshot, ROI-mean overlays.
4. Flesh out `notebooks/01_single_subject_walkthrough.ipynb` with real EMOP0649 outputs as living documentation.
5. End-to-end pipeline test using a tiny synthetic BIDS subject in `tests/data/`.
6. `mypy src/` pass — currently advisory-only in CI.
7. Notch-filter warning in `test_filters.py::test_notch_attenuates_injected_carrier` — synthetic raw is too short for the default notch length.
8. Switch `pyproject.toml` from `[tool.uv.dev-dependencies]` to `[dependency-groups.dev]` (deprecation warning).
9. Stim-artifact removal beyond surrogate-PLV: investigate template subtraction / SSP for the `active_stim` epochs if (1) shows the envelope dominating analyses.
10. v2 backlog: multi-subject group stats, SimNIBS/ROAST E-field modeling, ASHS hippocampal-subfield atlas, 3D nilearn brain plots.

---

## 7. Style rules baked into this codebase

(unchanged from v1 handoff — minimal comments, no preemptive abstractions, validate at boundaries only, pydantic v2 configs, structured logging)

---

## 8. Concrete first prompt for the next instance

> "Picking up TI_SEEG_Analysis_Pipeline (private repo bradyevan110/TI_SEEG_Analysis_Pipeline). Read HANDOFF.md for state. The pipeline is built and tested; the BIDS data for subject EMOP0649 is at `/Users/ebrady/Projects/SEEG Processing/` (or wherever you've placed it on this machine — update `bids_root` in the configs). Recreate `configs/subject_EMOP0649_run01.yaml` and `configs/subject_EMOP0649_run02.yaml` from the templates in §3 if they're missing, then run the cheap subset:
>
> ```bash
> uv run ti-seeg run --config configs/subject_EMOP0649_run01.yaml --steps preprocessing,anatomy,spectral
> ```
>
> If memory is plentiful, drop `crop` and raise `target_sfreq` to `null`. Verify the report.html looks sensible (1/f baseline PSD, 130 Hz peak in active_stim, 15 populated ROIs, no crashes). Then expand to the full pipeline and run-02. Report back before any code changes beyond config edits."
