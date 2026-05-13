"""Time-frequency representations via Morlet / multitaper."""

from __future__ import annotations

import mne
import numpy as np
from mne.time_frequency import tfr_morlet, tfr_multitaper

from ..config import PipelineConfig
from ..logging import get_logger

log = get_logger("tfr")


def _freqs(config: PipelineConfig) -> np.ndarray:
    cfg = config.tfr
    if cfg.freq_scale == "log":
        return np.logspace(np.log10(cfg.fmin), np.log10(cfg.fmax), cfg.n_freqs)
    return np.linspace(cfg.fmin, cfg.fmax, cfg.n_freqs)


def _n_cycles(freqs: np.ndarray, rule: str) -> np.ndarray:
    """Interpret rule like 'freqs / 2' or a numeric constant."""
    rule = rule.strip()
    if rule.startswith("freqs"):
        # Allow 'freqs / N' or 'freqs * N' or just 'freqs'.
        expr = rule.replace("freqs", "f")
        local = {"f": freqs, "np": np}
        return np.asarray(eval(expr, {"__builtins__": {}}, local), dtype=float)  # noqa: S307
    return np.full_like(freqs, float(rule), dtype=float)


def compute_tfr(
    epochs: mne.Epochs,
    config: PipelineConfig,
    picks: str | list[str] = "data",
    return_itc: bool = False,
) -> (
    mne.time_frequency.AverageTFR
    | tuple[mne.time_frequency.AverageTFR, mne.time_frequency.AverageTFR]
):
    cfg = config.tfr
    freqs = _freqs(config)
    n_cycles = _n_cycles(freqs, cfg.n_cycles_rule)
    log.info(
        "TFR method=%s, freqs=[%.1f..%.1f] (%d bins), n_cycles rule=%s",
        cfg.method,
        freqs[0],
        freqs[-1],
        len(freqs),
        cfg.n_cycles_rule,
    )

    kwargs = dict(
        freqs=freqs,
        n_cycles=n_cycles,
        picks=picks,
        return_itc=return_itc,
        average=True,
        decim=1,
        verbose="WARNING",
    )
    if cfg.method == "morlet":
        return tfr_morlet(epochs, **kwargs)
    if cfg.method == "multitaper":
        return tfr_multitaper(epochs, **kwargs)
    raise ValueError(f"Unknown TFR method: {cfg.method!r}")


def tfr_log_ratio_baseline(
    tfr: mne.time_frequency.AverageTFR,
    config: PipelineConfig,
) -> mne.time_frequency.AverageTFR:
    """Apply baseline normalization (in-place via MNE) using config.tfr.baseline.

    Clips the requested baseline window to the available epoch times. If no
    valid pre-zero overlap remains, skips correction with a warning rather
    than raising — some conditions (e.g. stim_test) have narrower windows.
    """
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
