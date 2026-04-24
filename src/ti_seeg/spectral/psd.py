"""PSD computation via MNE (multitaper / Welch), band aggregation, and contrasts."""

from __future__ import annotations

from dataclasses import dataclass

import mne
import numpy as np
import pandas as pd

from ..config import PipelineConfig
from ..logging import get_logger

log = get_logger("spectral.psd")


@dataclass
class PSDResult:
    freqs: np.ndarray  # (n_freqs,)
    psd: np.ndarray  # (n_channels, n_freqs)
    ch_names: list[str]
    condition: str


def compute_psd(
    epochs: mne.Epochs,
    config: PipelineConfig,
    condition: str,
) -> PSDResult:
    cfg = config.spectral
    log.info(
        "PSD [%s] method=%s fmin=%.1f fmax=%.1f bw=%.2f",
        condition,
        cfg.method,
        cfg.fmin,
        cfg.fmax,
        cfg.bandwidth_hz,
    )
    spectrum = epochs.compute_psd(
        method=cfg.method,
        fmin=cfg.fmin,
        fmax=cfg.fmax,
        bandwidth=cfg.bandwidth_hz if cfg.method == "multitaper" else None,
        verbose="WARNING",
    )
    data = spectrum.get_data()  # (n_epochs, n_channels, n_freqs)
    psd = data.mean(axis=0)  # average over epochs => (n_channels, n_freqs)
    return PSDResult(
        freqs=np.asarray(spectrum.freqs),
        psd=np.asarray(psd),
        ch_names=list(spectrum.ch_names),
        condition=condition,
    )


def aggregate_bands(
    result: PSDResult,
    bands: dict[str, list[float]],
) -> pd.DataFrame:
    """Return a tidy DataFrame of band-averaged power per channel."""
    rows = []
    for band_name, (lo, hi) in bands.items():
        mask = (result.freqs >= lo) & (result.freqs <= hi)
        if not mask.any():
            log.warning("No PSD bins in band %s [%s, %s]", band_name, lo, hi)
            continue
        band_power = result.psd[:, mask].mean(axis=1)
        for ch, p in zip(result.ch_names, band_power, strict=True):
            rows.append(
                {
                    "channel": ch,
                    "band": band_name,
                    "fmin": lo,
                    "fmax": hi,
                    "power": float(p),
                    "power_db": float(10 * np.log10(p + 1e-30)),
                    "condition": result.condition,
                }
            )
    return pd.DataFrame(rows)


def contrast_psds(
    a: PSDResult,
    b: PSDResult,
) -> pd.DataFrame:
    """Per-channel, per-freq log-ratio (10*log10(a/b))."""
    if not np.array_equal(a.freqs, b.freqs) or a.ch_names != b.ch_names:
        raise ValueError("Cannot contrast PSDs with mismatched freqs/channels.")
    ratio_db = 10 * np.log10((a.psd + 1e-30) / (b.psd + 1e-30))
    return pd.DataFrame(
        ratio_db,
        index=pd.Index(a.ch_names, name="channel"),
        columns=pd.Index(a.freqs, name="freq_hz"),
    )
