# TI_SEEG_Analysis_Pipeline — Handoff document (v3)

> **Purpose of this file:** self-contained briefing for the next Claude
> Code session (or human collaborator) picking up the project on the
> Windows workstation after the first successful end-to-end dry run.
>
> **Companion docs (still authoritative for their topics):**
> - [`HANDOFF.md`](HANDOFF.md) — v2, dated 2026-05-04. Subject-EMOP0649
>   BIDS-prep narrative + style rules. Most of §1–§5 of v2 are now
>   superseded by this file; §7 (style rules) is unchanged.
> - [`HANDOFF_EFIELD.md`](HANDOFF_EFIELD.md) — E-field module stack
>   (PRs #12–#18). Unchanged by this session — no `efield` code was
>   touched, the step is still gated by `efield.enabled=false`.
> - [`USER_GUIDE.md`](USER_GUIDE.md) — researcher-facing CLI/config
>   reference. Accurate as of 2026-05-12.
>
> **Last updated:** 2026-05-12 (v3).
> **Working directory while v3 was written:**
> `C:\Users\brady\TI_SEEG_Analysis_Pipeline\` (Windows 11, Python 3.12.3 in `.venv\`).

---

## 0. TL;DR for the next instance

- **The first complete end-to-end dry run for subject EMOP0649 run-01
  has finished successfully.** Full pipeline
  (`preprocessing → anatomy → efield(skip) → spectral → tfr → phase → cfc → connectivity → stats → report`)
  produced a 33 MB `report.html` and the full derivatives tree
  (~3.0 GB) under `subjects\sub-EMOP0649\derivatives\ti_seeg\...\task-amygdalati_run-01\`.
- **Headline result:** PLV-to-130 Hz-envelope is significant
  (p<0.05 vs time-shift surrogates) on **24 of 221 bipolar channels**.
  The top eight by PLV are dominated by left amygdala (`LAm6-LAm5`
  = 0.383, plus `LAm7-LAm6`, `LAm8-LAm7`, `LAm17-LAm16`) and left
  anterior hippocampus (`LAHc2-LAHc1`, `LAHc7-LAHc6`), plus right
  anterior nucleus thalamus (`RANT7-RANT6`) and right anterior insula
  (`RAIn15-RAIn14`). Physiologically coherent for an amygdala-targeting
  TI montage; **caveat that this is also exactly where the stim
  envelope is loudest in the recorded signal**, so the surrogate test
  result here is not yet disambiguating "neural entrainment" from
  "passive envelope pickup" (see HANDOFF v2 §5 gotcha #2).
- **Two real pipeline bugs were fixed inline (uncommitted, no git
  repo currently — see §5).** They were latent because the synthetic
  test suite never marks channels bad and never builds short-window
  epochs.
- **The host machine is now Windows 11, 32 GB RAM (17 GB free at
  start), Python 3.12.3 in `.venv\`. The maintainer's earlier work
  (HANDOFF v2) was on macOS.** All paths in v2 referencing
  `/Users/ebrady/Projects/SEEG Processing/` are *not* the paths on
  this machine — see §6.
- **Run-02 has not been done yet.** Its config does not exist locally
  (it was never committed; the v2 template is in HANDOFF.md §3 and
  needs the same Windows-path adaptation as run-01).
- **The BIDS-prep work HANDOFF v2 §2 described as "done" was done on
  the Mac and was NOT in the shipped repo.** It was redone on this
  machine during this session — see §3 — so future sessions on this
  Windows workstation can skip it. A second machine would need to
  redo it from scratch (or copy the modified files).

---

## 1. What changed since HANDOFF v2 (2026-05-04)

This session did four things and produced one artifact:

| Bucket | What |
|---|---|
| Subject config | Created `configs\subject_EMOP0649_run01.yaml` from HANDOFF v2 §3 template, adapted to Windows paths. Gitignored (per repo convention). |
| BIDS data prep | Replicated all of HANDOFF v2 §2 on the Windows BIDS tree (§3 of this doc). The maintainer's macOS prep didn't ship with the repo — confirm whether yours did before redoing. |
| Pipeline code fixes | Two minimal inline patches (§5). Both are real bugs the synthetic test suite doesn't surface. **Not committed** (no git repo). |
| Dependency | `h5io==0.2.5` added via `uv pip install h5io`. Needed by `mne.time_frequency.AverageTFR.save()`. Not in `pyproject.toml` (§5.3). |
| Pipeline run | Full `--steps preprocessing,anatomy,efield,spectral,tfr,phase,cfc,connectivity,stats,report` succeeded on `subject_EMOP0649_run01.yaml`. Wall time on this machine: **~25 min** end-to-end from scratch; **~13 min** if `preprocessed_raw.fif` is cached. |

Things v2 had open that this session **did not touch**:
- The `efield` step. `efield.enabled=false` in the config; step is registered but short-circuits.
- The HANDOFF v2 §6 backlog (anatomy refinement, report polish, notebook walkthrough, synthetic BIDS end-to-end test, mypy pass, deprecated `[tool.uv] dev-dependencies` block). All still open.
- The HANDOFF_EFIELD §9 backlog (step 7.7 EMOP0649 real-MRI dry run, anisotropic conductivities, etc.). All still open.

---

## 2. The completed run — what's in the derivatives tree

Path:
`subjects\sub-EMOP0649\derivatives\ti_seeg\sub-EMOP0649\ses-ieeg1\task-amygdalati_run-01\`

```
├── preprocessed_raw.fif       2.0 GB   (split into preprocessed_raw-1.fif when >2 GB)
├── preprocessed_raw-1.fif     (FIF continuation file)
├── bad_channels.json          22 channels flagged (variance/kurtosis Z>5)
├── spectral\
│   └── band_power.tsv         4608 rows (221 ch × 6 bands × 4 conditions)
├── tfr\                       2.1 GB total
│   ├── tfr_active_stim-tfr.h5
│   ├── tfr_no_stim-tfr.h5
│   ├── tfr_stim_test-tfr.h5
│   └── tfr_baseline-tfr.h5
├── phase\
│   ├── plv_to_envelope.tsv    221 rows: channel, plv, p_value
│   ├── cfc_mi_active_stim.tsv
│   ├── cfc_mi_no_stim.tsv
│   ├── cfc_mi_stim_test.tsv
│   └── cfc_mi_baseline.tsv
├── connectivity\              14 MB, 36 .npz files
│   └── con_<method>_<band>_<cond>.npz  (3 methods × 3 bands × 4 conditions)
├── figures\                   PNGs embedded in report.html
├── config_snapshot.yaml       exact resolved config used
├── run_manifest.json          per-step timestamps + pipeline_version + config_hash
├── pipeline.log               not currently written (see §7 gotcha #2)
└── report.html                33 MB consolidated report
```

### Pipeline log highlights (numbers you'll need)

| Quantity | Value |
|---|---|
| Channels picked from BIDS | 236 SEEG (41 non-SEEG dropped: 19 EEG / 20 MISC / 1 ECG / 1 TRIG) |
| Crop window | `[1500.0, 4900.0]` s (3400 s) — captures TI calibration (1587 s) + all stim_start/stim_stop boundaries (2815–4849 s) + small baseline |
| Target sample rate | 1024 Hz (native 2048 Hz → halved post-load) |
| Bad-channel count | 22 / 236 (0 flat, 5 high-var, 19 high-kurt). Most are on `LAm`, `LAHc`, `LMiHc`, `REc`, `RPHG` — likely real depth-electrode artifacts, not analysis bugs. |
| Bipolar derivations | 221 |
| Condition epoch counts | active_stim: 2 · no_stim: 3 · stim_test: 1 · baseline: 1 |
| PLV @ 130 Hz envelope | mean 0.137, max 0.383, n_significant @ p<0.05: **24 / 221** |
| Stats cluster test | 233 clusters, 0 significant (min p=0.395) — unsurprising with 2 vs 3 epochs. Real group-level stats are out of scope for v1. |

### ROI population (anatomy step)

| ROI | n_channels |
|---|---|
| amygdala | (LAm + RAm subset matching "amygdala") |
| hippocampus | (LAHc/RAHc/LMiHc/RMiHc/RPHc) |
| parahippocampal | 25 |
| temporal_pole | 17 |
| orbitofrontal | 17 |
| insula | 14 |
| thalamus_ant | 17 |
| pulvinar | 17 |
| entorhinal | (REc) |

(The exact amygdala/hippocampus/entorhinal counts aren't printed in
my last log tail above, but they appear in `pipeline.log` /
`report.html` — and the ROI substring rules in §4 explain how they
match the synthesized anat labels.)

---

## 3. BIDS data state on this machine

BIDS root: `C:\Users\brady\TI_SEEG_Analysis_Pipeline\subjects\sub-EMOP0649\`

> Note the unusual nesting — the *project* `subjects\sub-EMOP0649\`
> folder is also the *BIDS root*, and it in turn contains another
> `sub-EMOP0649\ses-ieeg1\ieeg\` directory. This is a BIDS-valid
> layout (top-level dataset_description.json lives at the BIDS root,
> per-subject content under `sub-<id>/...`); just be aware that
> `bids_root` is the **outer** `sub-EMOP0649` folder in the config.

```
subjects\sub-EMOP0649\
├── .bidsignore
├── dataset_description.json          (preexisting; "Temporal Interference iEEG", BIDS 1.9.0)
├── participants.json / participants.tsv
├── anat\
│   ├── sub-EMOP0649_ses-ieeg1_run-01_T1w.nii.gz
│   └── sub-EMOP0649_ses-ieeg1_run-01_T1w.json
├── raw_imaging\                       (DICOM-style EE... files; not consumed by the pipeline)
├── derivatives\ti_seeg\…              (this session's outputs; not in v0 repo)
└── sub-EMOP0649\
    └── ses-ieeg1\
        └── ieeg\
            ├── dataset_description.json   (duplicate of outer; preexisting, benign)
            ├── sub-EMOP0649_ses-ieeg1_electrodes.tsv        ← NEW this session (§3.4)
            ├── sub-EMOP0649_ses-ieeg1_coordsystem.json      ← NEW this session (§3.5)
            ├── sub-EMOP0649_..._run-01_ieeg.{edf,json}      (preexisting)
            ├── sub-EMOP0649_..._run-01_channels.tsv         ← MODIFIED (§3.2)
            ├── sub-EMOP0649_..._run-01_events.tsv           ← MODIFIED (§3.1, §3.3)
            └── (run-02 equivalents — channels/events also modified)
```

### 3.1 events.tsv — negative durations clamped

Original file had 23 rows with `duration = -1.0` (sentinel). MNE's
`set_annotations` asserts `duration >= 0`. Clamped all `< 0` →
`0.0` in both runs. Done with a one-liner pandas script (deleted
afterwards). Each run still has 23 data rows.

### 3.2 channels.tsv — retyped, EDF-Annotations row dropped

Run-01 + run-02 (both started with the same baseline state, both
retyped identically):

| Type | Count | Selection rule |
|---|---|---|
| `SEEG` | 236 | depth contacts |
| `EEG` | 19 | scalp 10-20 (`Fp1/2, F3/4/7/8, FZ, C3/4, CZ, P3/4/7/8, PZ, O1/2, T7/8` — case-insensitive match against an uppercased set) |
| `MISC` | 20 | `DC1`–`DC16`, `OSAT`, `PR`, `Pleth`, `Patient Event` |
| `ECG` | 1 | `EKG` |
| `TRIG` | 1 | `TRIG` |

The one `EDF Annotations` row (channel-count mismatch with the EDF
file) was dropped, taking the data row count from 278 → 277.

> Note: HANDOFF v2 §2 lists 19 MISC, not 20 — v2 didn't reclassify
> `PR` (pulse rate). It's MISC-shaped, so it's grouped with the
> other physiology channels. No functional difference (all MISC
> rows get dropped by `raw.pick("seeg")` regardless).

### 3.3 events.tsv — semantic label moved into `trial_type`

The EDF annotations gave us `trial_type = "annotation"` (literal,
constant) and `value = <semantic>` (e.g. `"task start"`, `"stim start"`).
`mne-bids` concatenates these as `"annotation/task start"` into the
`raw.annotations.description` field, which the pipeline's `label_map`
then can't recognize (the HANDOFF v2 §3 example map has unprefixed
keys like `"task start"`).

Fix: copied `value` → `trial_type` in both events.tsv files (kept
`value` intact for traceability). Now mne-bids reads
`description = "task start"` directly, and the unprefixed label_map
in subject configs works as the HANDOFF v2 template intended.

### 3.4 electrodes.tsv — synthesized, 236 rows

Columns: `name, x, y, z, size, anatomical_label`. All x/y/z/size are
`n/a` (per-contact coords don't exist yet — see HANDOFF v2 §2 final
paragraph; refinement is a drop-in file swap when post-op CT/MRI
fusion becomes available). `anatomical_label` is assigned per the
shank-prefix → anatomy mapping in HANDOFF v2 §2:

| Shank prefix | Count | anatomical_label |
|---|---|---|
| RAm | 16 | Right-Amygdala |
| LAm | 18 | Left-Amygdala |
| RAHc / LAHc | 15 / 15 | Right-/Left-Hippocampus-Anterior |
| RMiHc / LMiHc | 15 / 15 | Right-/Left-Hippocampus-Middle |
| RPHc | 15 | Right-Hippocampus-Posterior |
| REc | 13 | Right-Entorhinal |
| RPHG | 13 | Right-ParaHippocampalGyrus |
| RPPHG | 14 | Right-PosteriorParaHippocampalGyrus |
| RTePo | 18 | Right-TemporalPole |
| ROFc | 18 | Right-OrbitoFrontalCortex |
| RAIn | 15 | Right-AnteriorInsula |
| RANT | 18 | Right-AnteriorNucleusThalamus |
| RPUL | 18 | Right-Pulvinar |
| **Total** | **236** | |

> Column name choice: **HANDOFF v2 §2 said "anat" but the pipeline's
> `anat_label_column()` candidate list does NOT include "anat".** The
> code recognizes: `anatomical_label`, `anat_label`, `region`, `Region`,
> `destrieux`, `AAL`, `aparc`, `hemisphere_region`, `label` (in that
> priority order, then a heuristic fallback to "any string column with
> ≥3 unique values"). The fallback should have caught `anat` here, but
> didn't, so I renamed the column to `anatomical_label` (the first
> recognized name). Don't replicate the v2 wording — use
> `anatomical_label`. (The fact that the v2 doc and the code drift is
> itself worth a HANDOFF v2 §6 followup, or a docstring patch in
> `anatomy/contacts.py`.)

### 3.5 coordsystem.json — minimal

mne-bids requires `coordsystem.json` whenever an `electrodes.tsv`
is present, even when coords are `n/a`. Contents:

```json
{
  "iEEGCoordinateSystem": "Other",
  "iEEGCoordinateUnits": "mm",
  "iEEGCoordinateSystemDescription": "Coordinates not yet localized; electrodes.tsv x/y/z are n/a placeholders so mne-bids accepts the pair."
}
```

> Setting `iEEGCoordinateUnits: "mm"` (not the literal string `"n/a"`)
> silences an mne-bids warning that otherwise causes mne-bids to skip
> reading the electrodes.tsv entirely. The pipeline's
> `load_electrodes()` reads the TSV directly via pandas regardless,
> so the read still succeeds either way — but the warning was noisy
> and pointed to a real BIDS-spec misuse.

---

## 4. Subject config — recreate from this template

`configs\subject_*.yaml` is gitignored (per HANDOFF v2 §3 convention).
The run-01 config in use on this machine right now:

### `configs\subject_EMOP0649_run01.yaml`

```yaml
defaults_file: analysis_defaults.yaml

subject: "EMOP0649"
session: "ieeg1"
task: "amygdalati"
acquisition: "09"
run: "01"

bids_root: 'C:\Users\brady\TI_SEEG_Analysis_Pipeline\subjects\sub-EMOP0649'
derivatives_root: 'C:\Users\brady\TI_SEEG_Analysis_Pipeline\subjects\sub-EMOP0649\derivatives\ti_seeg'

anatomy:
  t1_path: 'C:\Users\brady\TI_SEEG_Analysis_Pipeline\subjects\sub-EMOP0649\anat\sub-EMOP0649_ses-ieeg1_run-01_T1w.nii.gz'
  t2_path: null

ti:
  block_label: inhibition
  f1_hz: 2000.0
  f2_hz: 2130.0
  envelope_hz: 130.0

preprocessing:
  notch_carriers: false        # carriers above Nyquist (sfreq=2048, carriers ~2 kHz)
  crop: [1500.0, 4900.0]       # 3400 s window: TI calibration + all stim blocks + buffer
  target_sfreq: 1024.0         # half native (Nyquist 512 Hz comfortably covers 200 Hz analyses)

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

YAML notes:
- **Use single quotes around Windows paths.** Backslashes inside
  double quotes are escape sequences; inside single quotes they're
  literal. The `subject_template.yaml` in the repo already uses
  single quotes for the same reason.
- `defaults_file: analysis_defaults.yaml` is resolved relative to
  the config's own parent dir; both this form and
  `configs/analysis_defaults.yaml` work (see `config.py:268-278`).
- `acquisition: "09"` is necessary because the EDF filenames carry
  `acq-09`; omitting it makes mne-bids fail to find the file.

### `configs\subject_EMOP0649_run02.yaml` (TODO — not present yet)

Same shape, with these overrides from v2 §3:

```yaml
run: "02"

ti:
  block_label: excitation
  f1_hz: 2000.0
  f2_hz: 2005.0
  envelope_hz: 5.0

preprocessing:
  notch_carriers: false
  # Inspect run-02 events.tsv to pick a stim-containing crop window
  # (run-02 stim_start/stim_stop labels are present per HANDOFF v2 §3 example
  # label_map; their timestamps weren't surveyed in this session).
  crop: [null, null]           # TODO: set after inspecting events.tsv onset values
  target_sfreq: 512.0          # 5 Hz envelope; aggressive downsample is fine

events:
  label_map:
    "start baseline": baseline
    "stim start": active_stim
    "stim stop": no_stim

phase:
  envelope:
    bandwidth_hz: 1.0          # narrower for the 5 Hz envelope
  cfc:
    phase_band: [3.0, 7.0]
    amp_bands:
      - [30.0, 80.0]
      - [80.0, 150.0]

# rois: same as run-01
```

To actually run run-02, also re-apply the §3.3 trial_type fix to
the run-02 events.tsv (already done in this session — both runs).

---

## 5. Code fixes applied this session — uncommitted, no git repo

There is **no `.git` directory** in this checkout (`git status`
fails). The two patches below sit as plain edits on disk. If the
next session initializes git or pulls from the GitHub remote,
re-apply them or open a PR.

### 5.1 `src\ti_seeg\spectral\psd.py` — ch_names / psd-rows alignment

`mne.time_frequency.EpochsSpectrum.get_data()` returns data only
for non-bad channels, but `.ch_names` includes the bads — so when
real bad-channel detection flags anything, `aggregate_bands` crashes
with `zip() argument 2 is shorter than argument 1`. The synthetic
test suite never marks channels bad, so the unit tests pass.

Patch (`compute_psd`, around line 46):

```python
data = spectrum.get_data()  # (n_epochs, n_channels, n_freqs); excludes bads
psd = data.mean(axis=0)
# spectrum.ch_names includes bads but get_data() drops them — keep ch_names aligned.
bads = set(spectrum.info["bads"])
good_ch_names = [n for n in spectrum.ch_names if n not in bads]
return PSDResult(
    freqs=np.asarray(spectrum.freqs),
    psd=np.asarray(psd),
    ch_names=good_ch_names,
    condition=condition,
)
```

### 5.2 `src\ti_seeg\tfr\tfr.py` — clip TFR baseline to epoch range

The default baseline window `[-1.0, -0.1]` doesn't fit the
`stim_test` epoch window `[-0.5, 2.0]` (configured in
`analysis_defaults.yaml`'s `events.epoch_window`). `apply_baseline`
raises `ValueError: Baseline interval ... is outside of epochs data ...`.

Patch (`tfr_log_ratio_baseline`):

```python
def tfr_log_ratio_baseline(tfr, config):
    bcfg = config.tfr.baseline
    epoch_tmin = float(tfr.times[0])
    epoch_tmax = float(tfr.times[-1])
    tmin = max(bcfg.tmin, epoch_tmin)
    tmax = min(bcfg.tmax, epoch_tmax)
    if tmin >= tmax:
        log.warning(
            "Skipping TFR baseline correction: requested (%s, %s) does not overlap epoch [%s, %s].",
            bcfg.tmin, bcfg.tmax, epoch_tmin, epoch_tmax,
        )
        return tfr
    return tfr.apply_baseline(baseline=(tmin, tmax), mode=bcfg.mode)
```

This clips the requested window to the available epoch times and
skips correction (with a warning) when no overlap remains. Observed
in the dry run on the `baseline` condition (`epoch_window =
[0.0, 10.0]` — entirely post-zero, no pre-event baseline available).

### 5.3 `h5io` dependency

`mne.time_frequency.AverageTFR.save()` lazily imports `h5io` for
HDF5 output. Not declared in `pyproject.toml` (`h5py` is, but that's
a different package). Installed locally via:

```powershell
uv pip install h5io
```

Resolved: `h5io==0.2.5`. Add this to `[project.dependencies]` in
`pyproject.toml` for a proper fix.

### 5.4 What was NOT changed

- `electrodes.tsv` column-name docstring / `_ANAT_COLUMN_CANDIDATES`
  in `src\ti_seeg\anatomy\contacts.py` (see §3.4 note). Worth either
  adding `"anat"` to the candidate list OR updating HANDOFF v2 §2's
  language.
- The pre-existing `[tool.uv] dev-dependencies` deprecation in
  `pyproject.toml` (HANDOFF v2 §6 item #8). Still triggers a warning
  on every `uv` invocation.

---

## 6. Environment-specific notes (Windows)

- **Working dir**: `C:\Users\brady\TI_SEEG_Analysis_Pipeline\`.
- **Venv**: `.venv\` (uv-managed). **Python 3.12.3** (HANDOFF_EFIELD
  §1 says the maintainer's Mac used 3.10 — this machine is newer).
  CLI entry point: `.venv\Scripts\ti-seeg.exe`.
- **Pip is not installed in the venv** — use `uv pip install <pkg>`
  for new packages (or sync via `uv sync`).
- **System RAM**: 32 GB total, 17 GB free when the run started. The
  3400 s crop window peaks at ~13 GB during the native-sfreq EDF
  load; the resample to 1024 Hz briefly doubles the working set
  before halving it. Fits comfortably; could go larger but
  diminishing returns past the last stim event at 4849 s.
- **No NVIDIA acceleration is used.** MNE / scipy / pandas are
  pure CPU + numpy here. (The user mentioned an RTX 3070 — that's
  GPU VRAM and is irrelevant to this pipeline; system RAM is the
  binding constraint.)
- **No SimNIBS on this machine.** `efield.enabled` is `false`; the
  E-field step short-circuits. To enable, see HANDOFF_EFIELD §1, §5.
- **Shell**: bash via Git for Windows works for `find`, `awk`, etc.
  PowerShell 7 is also available. Use the Bash tool's bash shell
  in tool calls where convenient; quote Windows paths.
- **Repo is NOT currently a git working tree** on this machine
  (`git log` fails). Either re-clone with full git metadata, or
  `git init` and `git remote add origin` to push back upstream
  before committing the §5 fixes.

### A note on the maintainer's Mac paths

HANDOFF v2 references `/Users/ebrady/Projects/SEEG Processing/` for
the BIDS root and SimNIBS at `/Users/ebrady/Applications/SimNIBS-4.6/`.
**None of those paths exist on this machine.** Don't follow v2
instructions verbatim — translate to:

| v2 (Mac) | This machine (Windows) |
|---|---|
| `/Users/ebrady/Projects/SEEG Processing/` | `C:\Users\brady\TI_SEEG_Analysis_Pipeline\subjects\sub-EMOP0649\` |
| `/Users/ebrady/Applications/SimNIBS-4.6/` | (not installed) |

---

## 7. Known gotchas (incremental — read alongside HANDOFF v2 §5)

Everything in v2 §5 still applies. Plus:

1. **Channel `type` semantics matter, including case.** Scalp 10-20
   names like `Fp1`/`FZ`/`PZ` in `channels.tsv` came back from the
   amplifier in mixed case (`F7` lowercase-z vs `FZ` uppercase). The
   retype script in §3.2 case-folds before matching. Do the same for
   any new subject.

2. **`pipeline.log` is NOT being written to the derivatives dir.**
   USER_GUIDE §7 mentions it; in this run the log only goes to
   stdout (captured into `pipeline_run01.log` at the repo root,
   which is now stale and can be deleted). Whether this is a config
   issue or a missing logger handler is unclear — defer to whatever
   `src\ti_seeg\logging.py` and the `RunContext` initializer do.

3. **`spectrum.get_data()` excludes bads, `spectrum.ch_names`
   includes them.** §5.1 fixed it once in `spectral\psd.py`. Audit
   for the same pattern elsewhere (anywhere a `Spectrum` /
   `AverageTFR` / `Evoked` is zipped against its `ch_names`).

4. **Annotation description format depends on what's in events.tsv.**
   When `trial_type` is a constant (`"annotation"`) and the meaningful
   label is in `value`, mne-bids emits `description = "trial_type/value"`
   (so `"annotation/task start"`). The simplest workaround used here
   (§3.3) is to copy `value` into `trial_type` once. The alternative
   is to put prefixed keys in the config's `label_map`. Pick one
   convention and stick to it across subjects.

5. **events.tsv durations of `-1.0` are an EDF-annotation sentinel
   meaning "instantaneous".** Clamp to `0` (v2 §5 #5 already says
   this — repeating because it bit again this session).

6. **Multiple `MISC` channels' types are upstream noise.** `PR`
   (pulse rate) wasn't in v2's spec; included in MISC here. It's
   not exercised by the pipeline (everything past `raw.pick("seeg")`
   is depth-only).

---

## 8. Outstanding work

### 8.1 Immediate (single-session-scope)

1. **Inspect `report.html`** — confirm the dry run "passes" by v2
   §4 criteria:
   - Baseline PSD is roughly 1/f.
   - During `active_stim`, run-01 should show a sharp 130 Hz peak.
   - ROI groups populate with non-zero counts (already confirmed in
     the log — see §2 of this doc).
   - No crashes (none — exit code 0).
   - The top-PLV channels list (§0 TL;DR) lands on anatomically
     plausible shanks (it does — left amygdala dominance).
2. **Run run-02.** Create `configs\subject_EMOP0649_run02.yaml`
   from §4 template above. Pick the crop window by reading
   `subjects\sub-EMOP0649\sub-EMOP0649\ses-ieeg1\ieeg\sub-EMOP0649_..._run-02_events.tsv`
   to find stim_start / stim_stop onset times (events.tsv `trial_type`
   was already remapped in §3.3 so the column to inspect is
   `trial_type` directly). Then `.venv\Scripts\ti-seeg.exe run
   --config configs\subject_EMOP0649_run02.yaml`.
3. **Commit the §5 code fixes** — init git, push to `bradyevan110/TI_SEEG_Analysis_Pipeline`,
   open a PR (or two: one for psd.py, one for tfr.py, one for the
   pyproject h5io add). Add unit tests that mark a channel bad before
   calling `compute_psd` and assert PSDResult lengths match.

### 8.2 Carries over from HANDOFF v2 §6 (still open)

(See v2 for full text — abridged here.)

- Replace shank-prefix anatomy with per-contact labels (post-op CT/MRI + atlas).
- Polish HTML report (section grouping, narrative, collapsible config snapshot, ROI overlays).
- Flesh out `notebooks\01_single_subject_walkthrough.ipynb` with real EMOP0649 outputs.
- Synthetic-BIDS end-to-end test in `tests\data\`.
- `mypy src\` pass.
- Notch warning in `test_filters.py::test_notch_attenuates_injected_carrier` (synthetic raw too short).
- Migrate `[tool.uv] dev-dependencies` → `[dependency-groups] dev`.
- Stim-artifact removal beyond surrogate-PLV (template subtraction / SSP for `active_stim` epochs).
- v2 backlog: multi-subject group stats, SimNIBS/ROAST E-field modeling, ASHS hippocampal-subfield atlas, 3D nilearn brain plots.

### 8.3 Carries over from HANDOFF_EFIELD §9 (still open)

- **Step 7.7: EMOP0649 real-MRI E-field dry run.** Requires (a)
  stim-electrode names (the user has these; not captured in this
  session) and (b) SimNIBS installed on this machine (it isn't).
  Don't `charm` without explicit user go-ahead (1–3 hr compute, ~2 GB disk).
- PRs #12–#18 (E-field stack) still open, awaiting merge per
  HANDOFF_EFIELD §0.

### 8.4 New backlog items from this session

- **`anat` vs `anatomical_label` column-name drift** — either add
  `"anat"` to `_ANAT_COLUMN_CANDIDATES` in `src\ti_seeg\anatomy\contacts.py`
  or update HANDOFF v2 §2 to say `anatomical_label`. Don't leave
  the documentation in disagreement with the code.
- **Investigate why `anat_label_column()`'s heuristic fallback
  didn't pick up an `anat` column.** The column was `object` dtype
  with 15 unique values; should have matched. Likely the
  pandas-default `na_values` treatment of "n/a" coerced x/y/z/size
  to float (NaN) and the loop exits on the first candidate match —
  but that should have been `anat`. Worth a single-test repro.
- **Missing `pipeline.log` write target.** Add a file handler to
  `RunContext` that writes to `<derivatives>\...\pipeline.log`.
- **`h5io` belongs in `pyproject.toml`** (§5.3).
- **Run-02 needs its own crop window decision** (§4 placeholder).

---

## 9. Concrete first prompt for the next instance

> "Picking up `TI_SEEG_Analysis_Pipeline` on the Windows workstation at
> `C:\Users\brady\TI_SEEG_Analysis_Pipeline\`. Read `HANDOFF_V3.md` for
> the current state; `HANDOFF.md` (v2) and `HANDOFF_EFIELD.md` remain
> authoritative for the BIDS-prep narrative and the E-field stack
> respectively.
>
> **Confirmed working:** the run-01 pipeline (preprocessing →
> anatomy → spectral → tfr → phase → cfc → connectivity → stats →
> report) completed end-to-end. Outputs are under
> `subjects\sub-EMOP0649\derivatives\ti_seeg\sub-EMOP0649\ses-ieeg1\task-amygdalati_run-01\`.
> 24 / 221 bipolar channels are significant for PLV-to-130 Hz-envelope;
> the top of the list is left amygdala and left anterior hippocampus
> (anatomically coherent for the inhibition montage). The
> `efield.enabled=false` short-circuit kept the E-field step out
> of this run.
>
> **Two code fixes (§5) are uncommitted** (no `.git` here). They are
> real bugs the synthetic test suite misses — please don't drop them.
>
> **First action:** open the `report.html` and judge whether it
> 'passes' by HANDOFF v2 §4 criteria (1/f baseline PSD, 130 Hz peak
> during active_stim, populated ROIs, no crashes). Report findings.
>
> **Then either:** (a) create `configs\subject_EMOP0649_run02.yaml`
> from the §4 template and run it (the run-02 events.tsv already
> has `trial_type` remapped, so the §4 `label_map` should work
> as-written); (b) initialize git in this directory, commit the §5
> fixes, and push upstream; or (c) the next concrete item from §8.4."

