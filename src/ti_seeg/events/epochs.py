"""Epoching: condition-locked and sliding windows."""

from __future__ import annotations

import mne
import numpy as np
import pandas as pd

from ..config import PipelineConfig
from ..logging import get_logger

log = get_logger("events.epochs")


def select_condition_events(events_df: pd.DataFrame, condition: str) -> pd.DataFrame:
    """Return rows of events_df whose `canonical` label equals `condition`."""
    if events_df.empty or "canonical" not in events_df.columns:
        return events_df.iloc[0:0]
    return events_df[events_df["canonical"] == condition].reset_index(drop=True)


def _events_array_from_df(df: pd.DataFrame, sfreq: float, event_id: int) -> np.ndarray:
    onsets = (df["onset"].to_numpy() * sfreq).round().astype(int)
    arr = np.zeros((len(onsets), 3), dtype=int)
    arr[:, 0] = onsets
    arr[:, 2] = event_id
    return arr


def make_condition_epochs(
    raw: mne.io.BaseRaw,
    events_df: pd.DataFrame,
    config: PipelineConfig,
    conditions: list[str] | None = None,
) -> dict[str, mne.Epochs]:
    """Return a dict {condition: Epochs} based on events.tsv and per-condition windows.

    Conditions without a configured epoch_window are skipped with a warning.
    """
    cfg_windows = config.events.epoch_window or {}
    conditions = conditions or list(cfg_windows.keys())

    out: dict[str, mne.Epochs] = {}
    for cond in conditions:
        if cond not in cfg_windows:
            log.warning("No epoch_window configured for '%s'; skipping.", cond)
            continue
        rows = select_condition_events(events_df, cond)
        if rows.empty:
            log.warning("No events with canonical=='%s'; skipping.", cond)
            continue
        tmin, tmax = cfg_windows[cond]
        events_arr = _events_array_from_df(rows, raw.info["sfreq"], event_id=1)
        epochs = mne.Epochs(
            raw,
            events=events_arr,
            event_id={cond: 1},
            tmin=tmin,
            tmax=tmax,
            baseline=None,
            preload=True,
            reject_by_annotation=False,
            verbose="WARNING",
        )
        log.info("Built %d epochs for '%s' (tmin=%.2f, tmax=%.2f)", len(epochs), cond, tmin, tmax)
        out[cond] = epochs
    return out


def make_sliding_epochs(
    raw: mne.io.BaseRaw,
    config: PipelineConfig,
    start_sec: float | None = None,
    stop_sec: float | None = None,
) -> mne.Epochs:
    """Make non-event-locked fixed-length epochs over a time range for continuous analyses."""
    sliding = config.events.sliding
    sfreq = raw.info["sfreq"]
    win = sliding.window_sec
    step = win * (1.0 - sliding.overlap)
    if step <= 0:
        raise ValueError("Sliding step must be positive; check overlap < 1.")
    start_sec = 0.0 if start_sec is None else start_sec
    stop_sec = raw.times[-1] if stop_sec is None else stop_sec

    onsets = np.arange(start_sec, stop_sec - win, step)
    events_arr = np.zeros((len(onsets), 3), dtype=int)
    events_arr[:, 0] = (onsets * sfreq).round().astype(int)
    events_arr[:, 2] = 1
    epochs = mne.Epochs(
        raw,
        events=events_arr,
        event_id={"sliding": 1},
        tmin=0.0,
        tmax=win,
        baseline=None,
        preload=True,
        verbose="WARNING",
    )
    log.info(
        "Built %d sliding epochs (window=%.2fs, overlap=%.2f) over [%.1f, %.1f]s",
        len(epochs),
        win,
        sliding.overlap,
        start_sec,
        stop_sec,
    )
    return epochs
