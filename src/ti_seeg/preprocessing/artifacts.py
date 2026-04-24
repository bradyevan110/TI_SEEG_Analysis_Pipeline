"""Bad-channel detection for SEEG."""

from __future__ import annotations

import json
from pathlib import Path

import mne
import numpy as np
from scipy import stats

from ..config import PipelineConfig
from ..logging import get_logger

log = get_logger("preprocessing.artifacts")


def detect_bad_channels(
    raw: mne.io.BaseRaw,
    config: PipelineConfig,
    out_path: Path | None = None,
) -> list[str]:
    """Flag bad channels via flatness, variance, and kurtosis z-scores.

    Uses a random subset of the recording (up to 60 s) for robustness.
    """
    strategy = config.preprocessing.bad_channel_strategy
    if strategy.method == "none":
        return []
    if strategy.method == "manual":
        # Caller sets raw.info['bads'] directly.
        return list(raw.info["bads"])

    # variance_kurtosis
    sfreq = raw.info["sfreq"]
    n_samples = raw.n_times
    max_samples = int(min(60 * sfreq, n_samples))
    start = 0
    stop = max_samples
    data = raw.get_data(start=start, stop=stop, picks="data")

    # Per-channel stats
    std = data.std(axis=1)
    kurt = stats.kurtosis(data, axis=1, fisher=True)

    # Convert to microvolts for flatness check (data is in volts in MNE).
    std_uv = std * 1e6
    flat_mask = std_uv < strategy.flat_thresh_uv

    # Robust z-scores.
    def _zscore(x: np.ndarray) -> np.ndarray:
        med = np.median(x)
        mad = np.median(np.abs(x - med)) + 1e-12
        return 0.6745 * (x - med) / mad

    var_z = np.abs(_zscore(std))
    kurt_z = np.abs(_zscore(kurt))
    high_var = var_z > strategy.variance_z_thresh
    high_kurt = kurt_z > strategy.kurtosis_z_thresh

    bad_mask = flat_mask | high_var | high_kurt
    ch_names = raw.copy().pick("data").ch_names
    bad_channels = [ch for ch, bad in zip(ch_names, bad_mask, strict=True) if bad]

    log.info(
        "Bad channels: %d / %d (flat=%d, high_var=%d, high_kurt=%d)",
        len(bad_channels),
        len(ch_names),
        int(flat_mask.sum()),
        int(high_var.sum()),
        int(high_kurt.sum()),
    )

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(
                {
                    "bad_channels": bad_channels,
                    "reasons": {
                        ch: {
                            "flat": bool(flat_mask[i]),
                            "high_var": bool(high_var[i]),
                            "high_kurt": bool(high_kurt[i]),
                            "std_uv": float(std_uv[i]),
                            "var_z": float(var_z[i]),
                            "kurt_z": float(kurt_z[i]),
                        }
                        for i, ch in enumerate(ch_names)
                        if bad_mask[i]
                    },
                    "strategy": strategy.model_dump(),
                },
                f,
                indent=2,
            )
        log.info("Wrote bad-channel report: %s", out_path)

    return bad_channels
