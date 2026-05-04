"""BIDS iEEG loading built on mne-bids."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mne
import pandas as pd

from ..config import PipelineConfig
from ..logging import get_logger

log = get_logger("io")


@dataclass
class BIDSSubjectData:
    """Container for everything we pull out of BIDS for a single (subject, run)."""

    raw: mne.io.BaseRaw
    electrodes: pd.DataFrame  # one row per channel w/ coords + anat labels
    events: pd.DataFrame  # columns: onset, duration, trial_type, ...
    bids_path: "object"  # mne_bids.BIDSPath


def _build_bids_path(config: PipelineConfig):
    # Deferred import so that `import ti_seeg` does not require mne-bids at import time.
    from mne_bids import BIDSPath

    return BIDSPath(
        subject=config.subject,
        session=config.session,
        task=config.task,
        run=config.run,
        acquisition=config.acquisition,
        datatype="ieeg",
        root=config.bids_root,
        suffix="ieeg",
        extension=".edf",
        check=False,
    )


def load_subject(config: PipelineConfig) -> BIDSSubjectData:
    """Load raw iEEG + electrodes + events for the subject/run in the config."""
    from mne_bids import read_raw_bids

    bids_path = _build_bids_path(config)
    log.info("Loading BIDS: %s", bids_path.basename)

    raw = read_raw_bids(bids_path, verbose="WARNING")

    n_total = len(raw.ch_names)
    raw.pick("seeg")
    n_kept = len(raw.ch_names)
    if n_kept < n_total:
        log.info("Picked %d SEEG channels (dropped %d non-SEEG).", n_kept, n_total - n_kept)

    crop = config.preprocessing.crop or [None, None]
    tmin, tmax = (list(crop) + [None, None])[:2]
    if tmin is not None or tmax is not None:
        log.info("Cropping raw to [%s, %s] sec before load.", tmin, tmax)
        raw.crop(tmin=tmin or 0.0, tmax=tmax)

    raw.load_data()

    target_sfreq = config.preprocessing.target_sfreq
    if target_sfreq is not None and target_sfreq < raw.info["sfreq"]:
        log.info("Resampling %.1f -> %.1f Hz.", raw.info["sfreq"], target_sfreq)
        raw.resample(target_sfreq, verbose="WARNING")

    electrodes = load_electrodes(config)
    events = load_events(raw, config)

    return BIDSSubjectData(raw=raw, electrodes=electrodes, events=events, bids_path=bids_path)


def load_electrodes(config: PipelineConfig) -> pd.DataFrame:
    """Read electrodes.tsv. mne-bids places it at <sub>/<ses>/ieeg/*_electrodes.tsv."""
    subject_dir = Path(config.bids_root) / f"sub-{config.subject}"
    if config.session:
        subject_dir = subject_dir / f"ses-{config.session}"
    ieeg_dir = subject_dir / "ieeg"
    matches = sorted(ieeg_dir.glob("*_electrodes.tsv"))
    if not matches:
        raise FileNotFoundError(f"No *_electrodes.tsv found under {ieeg_dir}")
    if len(matches) > 1:
        log.warning("Multiple electrodes.tsv found; using %s", matches[0].name)
    df = pd.read_csv(matches[0], sep="\t")
    df.columns = [c.strip() for c in df.columns]
    return df


def load_events(raw: mne.io.BaseRaw, config: PipelineConfig) -> pd.DataFrame:
    """Pull events from raw.annotations (populated by mne-bids from events.tsv)
    and normalize `trial_type` via the config label map."""
    ann = raw.annotations
    if len(ann) == 0:
        log.warning("No annotations found on Raw — events.tsv may be empty/missing.")
        return pd.DataFrame(columns=["onset", "duration", "trial_type", "canonical"])

    df = pd.DataFrame(
        {
            "onset": ann.onset,
            "duration": ann.duration,
            "trial_type": ann.description,
        }
    )

    label_map = config.events.label_map or {}
    df["canonical"] = df["trial_type"].map(
        lambda lbl: label_map.get(lbl, label_map.get(lbl.lower(), lbl))
    )
    return df


def validate_subject_data(
    data: BIDSSubjectData, config: PipelineConfig, strict: bool = False
) -> list[str]:
    """Cross-check sampling rate vs. TI carriers, channel consistency, event labels.

    Returns a list of warning messages. If `strict`, raises on any issue.
    """
    warnings_list: list[str] = []
    sfreq = data.raw.info["sfreq"]
    max_carrier = max(config.ti.carriers)
    if sfreq < 4 * max_carrier:
        warnings_list.append(
            f"Sampling rate {sfreq} Hz is <4x highest carrier ({max_carrier} Hz) — "
            "carrier notching and envelope extraction may alias."
        )

    n_raw_channels = len(data.raw.ch_names)
    n_elec_rows = len(data.electrodes)
    if n_raw_channels != n_elec_rows:
        warnings_list.append(
            f"Raw has {n_raw_channels} channels but electrodes.tsv has {n_elec_rows} rows."
        )

    if data.events.empty:
        warnings_list.append("No events parsed from events.tsv/annotations.")
    else:
        known = set((config.events.label_map or {}).values()) | {
            "baseline",
            "stim_test",
            "active_stim",
            "no_stim",
        }
        unknown = set(data.events["canonical"].dropna()) - known
        if unknown:
            warnings_list.append(f"Unknown canonical event labels present: {sorted(unknown)}")

    for msg in warnings_list:
        log.warning(msg)
    if strict and warnings_list:
        raise RuntimeError("Validation failed:\n  - " + "\n  - ".join(warnings_list))
    return warnings_list
