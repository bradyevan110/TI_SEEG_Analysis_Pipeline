# TI_SEEG_Analysis_Pipeline — Handoff document (v4)

> **Purpose:** incremental briefing for the next session, after run-02
> completed and the v3 §8.4 cleanups were addressed.
>
> **Companion docs:**
> - [`HANDOFF.md`](HANDOFF.md) — v2 (BIDS-prep narrative, style rules).
> - [`HANDOFF_V3.md`](HANDOFF_V3.md) — v3 (run-01 dry run, code fixes, env notes). **Still authoritative** for everything not superseded here.
> - [`HANDOFF_EFIELD.md`](HANDOFF_EFIELD.md) — E-field module (unchanged this session; `efield.enabled=false` short-circuit still in effect).
> - [`USER_GUIDE.md`](USER_GUIDE.md) — researcher-facing CLI/config reference.
>
> **Last updated:** 2026-05-14 (v4).

---

## 0. TL;DR

- **Run-02 completed end-to-end** in ~7 min (vs run-01's 25 min — the 512 Hz target sfreq is responsible). Outputs at `subjects\sub-EMOP0649\derivatives\ti_seeg\sub-EMOP0649\ses-ieeg1\task-amygdalati_run-02\`. `report.html` is 28 MB; `preprocessed_raw.fif` is 1.4 GB.
- **Headline result:** PLV-to-5-Hz-envelope is significant on **12 of 221 bipolar channels** (vs 24/221 at 130 Hz for run-01). Top significant channels are **right temporal pole / right anterior nucleus thalamus / right posterior hippocampus / right parahippocampal** — qualitatively different from run-01's left-amygdala dominance, consistent with the different montage (excitation block, f1=2000 Hz, f2=2005 Hz). Same envelope-pickup caveat from v3 §0 applies.
- **All v3 §8.4 backlog items are addressed.** h5io was already declared in `pyproject.toml`; `anat` is now a first-class candidate column in `_ANAT_COLUMN_CANDIDATES`; `pipeline.log` is now actually written to the derivatives dir.
- **Git state:** still on branch `fix/dry-run-real-data-bugs`, ahead of `main`. Branch holds the v3 §5 fixes plus the v4 cleanups. PR is the natural next action (v3 §5 fixes have not yet merged to main).

---

## 1. Run-02 results

### 1.1 Pipeline numbers

| Quantity | Value |
|---|---|
| Wall time | ~7 min (from cold) |
| Channels picked from BIDS | 236 SEEG (41 non-SEEG dropped) |
| Crop window | `[1300.0, 4400.0]` s (3100 s) — covers task start (1333) through End Block 2 (4388), incl. [-1, +10] epoch buffers around stim_start (1382/2383/3607) and stim_stop (2028/3017/4250) |
| Target sample rate | 512 Hz (Nyquist 256 — comfortably covers fmax=200 analyses) |
| Bad-channel count | 20 / 236 (0 flat, 7 high-var, 15 high-kurt). Most on `LAm`, `LAHc`, `LMiHc`, `RAm`, `RAHc`, `RPHG`, `RPHc` — same shanks as run-01, slightly different per-contact selection. |
| Bipolar derivations | 221 |
| Condition epoch counts | active_stim: 3 · no_stim: 3 · baseline: 1 · stim_test: 0 (correctly absent — run-02 has no calibration block) |
| PLV @ 5 Hz envelope | mean 0.134, max 0.380, n_significant @ p<0.05: **12 / 221** |
| CFC theta→gamma Tort MI | low-gamma mean ≈ 0.001, high-gamma mean ≈ 0.001 (noise-floor-ish) |
| Stats cluster test | 204 clusters, 0 significant (min p=0.519) — same low-power story as run-01 (3 vs 3 epochs) |

### 1.2 Top significant PLV channels

```
      channel       plv  p_value
RTePo2-RTePo1     0.338  0.005    right temporal pole
RANT9-RANT8       0.315  0.005    right anterior nucleus thalamus
RPHc4-RPHc3       0.315  0.015    right posterior hippocampus
RPHG13-RPHG12     0.296  0.005    right parahippocampal
RPHG5-RPHG4       0.274  0.025    right parahippocampal
LMiHc7-LMiHc6     0.250  0.045    left mid-hippocampus
RPHG9-RPHG8       0.244  0.020    right parahippocampal
RPHG11-RPHG10    0.235  0.005    right parahippocampal
RAHc14-RAHc13     0.228  0.005    right anterior hippocampus
LAm13-LAm12       0.223  0.005    left amygdala
```

The qualitative shift from run-01's left-amygdala dominance to a
right-hemisphere parahippocampal/thalamic pattern is consistent with
the different TI montage. **As with run-01, this is also where the 5 Hz
envelope would be loudest from passive pickup — surrogate test cannot
disambiguate entrainment from pickup.**

### 1.3 Observations from the log

- "Sampling rate 512 Hz is <4× highest carrier (2005 Hz)" warning fires (expected — `notch_carriers=false`; carriers are above Nyquist either way and are suppressed by the implicit lowpass during the 2048→512 downsample).
- The §5.2 baseline-clipping fix actually fires on run-02's `baseline` condition: "Skipping TFR baseline correction: requested (-1.0, -0.1) does not overlap epoch [0.0, 10.0]." Same as run-01.
- `pipeline.log` is now written to the derivatives dir (see §2.3).

---

## 2. Code changes this session

### 2.1 `src\ti_seeg\anatomy\contacts.py` — `anat` is now a recognized column

`_ANAT_COLUMN_CANDIDATES` previously listed `anatomical_label`, `anat_label`, `region`, etc., but **not** `anat` — even though HANDOFF v2 §2 documents `anat` as the column name. This caused the v3 author to rename the column during BIDS prep. Added `anat` to the candidate list (3rd position, after the more explicit variants). New unit test in `tests/test_anatomy.py::test_anat_label_column_recognizes_short_anat`.

### 2.2 `src\ti_seeg\logging.py` — `setup_logger` is now re-entry-safe

Old behavior: `setup_logger()` set `_ti_seeg_configured=True` on first call and **early-returned** on subsequent calls. The CLI calls it once with no args (cli.py:34), then `run_pipeline` calls it again with `log_file=...` (pipeline/run.py:452) — but the second call short-circuited, so the file handler was never attached and `pipeline.log` was never written.

Fix: split the idempotency into two flags (`_ti_seeg_configured` for the stream handler, `_ti_seeg_file_handler` for the file handler). The second call now attaches the file handler if it hasn't been attached yet. Two unit tests in `tests/test_logging.py`.

### 2.3 `pipeline.log` now actually exists in the derivatives dir

Consequence of §2.2. Verifiable: `subjects\sub-EMOP0649\derivatives\ti_seeg\sub-EMOP0649\ses-ieeg1\task-amygdalati_run-0X\pipeline.log` will be written by the next pipeline invocation. (The existing run-02 outputs from this session do **not** have one — that run was finished before the fix landed.)

### 2.4 New subject config

`configs\subject_EMOP0649_run02.yaml` was authored (gitignored per repo convention). Captured here for reproducibility:

```yaml
defaults_file: analysis_defaults.yaml
subject: "EMOP0649"
session: "ieeg1"
task: "amygdalati"
acquisition: "09"
run: "02"
bids_root: 'C:\Users\brady\TI_SEEG_Analysis_Pipeline\subjects\sub-EMOP0649'
derivatives_root: 'C:\Users\brady\TI_SEEG_Analysis_Pipeline\subjects\sub-EMOP0649\derivatives\ti_seeg'
anatomy:
  t1_path: 'C:\Users\brady\TI_SEEG_Analysis_Pipeline\subjects\sub-EMOP0649\anat\sub-EMOP0649_ses-ieeg1_run-01_T1w.nii.gz'
  t2_path: null
ti:
  block_label: excitation
  f1_hz: 2000.0
  f2_hz: 2005.0
  envelope_hz: 5.0
preprocessing:
  notch_carriers: false
  crop: [1300.0, 4400.0]
  target_sfreq: 512.0
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

### 2.5 What was NOT changed

- `[tool.uv] dev-dependencies` deprecation in `pyproject.toml` (v2 §6, v3 §8.2). Still triggers a warning on every `uv` invocation; not addressed.
- `tfr_morlet()` legacy-API NOTE prints (lines like "tfr_morlet() is a legacy function. New code should use .compute_tfr(method='morlet')."). Cosmetic; ignored.
- Pre-existing v3 §8.2 backlog (anatomy refinement, report polish, notebook walkthrough, synthetic BIDS test, mypy pass, stim-artifact removal).
- The pre-existing `test_filters.py::test_notch_attenuates_injected_carrier` notch warning (synthetic raw too short for the notch filter length). Cosmetic; pytest still passes.

---

## 3. Test suite state

After this session: **44 tests pass, 2 skipped** (the existing skipped tests are headless-Linux pyvista and slow FEM smoke). New additions:

- `tests/test_anatomy.py::test_anat_label_column_recognizes_short_anat`
- `tests/test_logging.py::test_setup_logger_attaches_file_handler_after_bare_call`
- `tests/test_logging.py::test_setup_logger_does_not_double_attach_file_handler`

---

## 4. Git state

| | |
|---|---|
| Branch | `fix/dry-run-real-data-bugs` |
| Base | `main` |
| Ahead of main by | run-01 §5 fixes (3 commits), v3 handoff doc (1 commit), this session's changes (TBD on commit) |
| PR | Not yet opened. See §6. |

---

## 5. Outstanding work

### 5.1 Immediate

1. **Commit this session's changes** and **open a PR** for `fix/dry-run-real-data-bugs` → `main`. The branch is now a sensible review unit: real-data bugs from run-01, docs, and the v4 cleanups.
2. **Compare `report.html` for run-01 vs run-02 side by side** to corroborate the qualitative shift (left amygdala 130 Hz vs right parahippocampal/thalamic 5 Hz). Useful for the methods narrative in any forthcoming write-up.
3. **Re-run run-01 or run-02 with the §2.2 fix in place** if you want a `pipeline.log` artifact on disk for either run. Optional — the existing `pipeline_run01.log` / `pipeline_run02.log` at the repo root (stdout captures) carry the same content.

### 5.2 Carries forward from HANDOFF v3 §8.2 (still open)

- Replace shank-prefix anatomy with per-contact labels (post-op CT/MRI + atlas).
- Polish HTML report (section grouping, narrative, collapsible config snapshot, ROI overlays).
- Flesh out `notebooks\01_single_subject_walkthrough.ipynb` with real EMOP0649 outputs.
- Synthetic-BIDS end-to-end test in `tests\data\`.
- `mypy src\` pass.
- Migrate `[tool.uv] dev-dependencies` → `[dependency-groups] dev`.
- Stim-artifact removal beyond surrogate-PLV (template subtraction / SSP for `active_stim` epochs).
- Multi-subject group stats, SimNIBS/ROAST E-field modeling, ASHS hippocampal-subfield atlas, 3D nilearn brain plots.

### 5.3 Carries forward from HANDOFF_EFIELD §9 (still open)

- **Step 7.7: EMOP0649 real-MRI E-field dry run.** Still requires (a) stim-electrode names + (b) SimNIBS installed on this machine.
- PRs #12–#18 (E-field stack) still open per HANDOFF_EFIELD §0.

---

## 6. Concrete first prompt for the next instance

> "Picking up `TI_SEEG_Analysis_Pipeline` on the Windows workstation at
> `C:\Users\brady\TI_SEEG_Analysis_Pipeline\`. Read `HANDOFF_V4.md` for
> the latest state; v3 / v2 / HANDOFF_EFIELD are companion docs.
>
> **Confirmed working:** both run-01 (inhibition / 130 Hz envelope) and
> run-02 (excitation / 5 Hz envelope) pipelines completed end-to-end on
> EMOP0649. Run-02 shows 12/221 channels significant for PLV-to-envelope,
> top of the list dominated by right temporal pole / right ANT / right
> parahippocampal. The §2 cleanups (anat column, pipeline.log handler)
> are in place plus unit tests.
>
> **First action:** if a PR for `fix/dry-run-real-data-bugs` → `main`
> isn't already open, open one. Then decide: (a) start on a v3 §8.2
> item from the backlog, or (b) start a real-MRI E-field dry run per
> HANDOFF_EFIELD §9 step 7.7 (requires SimNIBS install + stim-electrode
> names)."
