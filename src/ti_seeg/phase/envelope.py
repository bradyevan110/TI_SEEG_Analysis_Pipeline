"""Narrowband Hilbert helpers + TI envelope extraction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt

from ..logging import get_logger

log = get_logger("phase.envelope")


def bandpass_hilbert(
    data: np.ndarray,
    sfreq: float,
    f_center: float,
    bandwidth: float,
    order: int = 4,
) -> tuple[np.ndarray, np.ndarray]:
    """Zero-phase bandpass, then Hilbert. Returns (amplitude, phase) arrays same shape as data.

    Works on 1D or (..., n_times) arrays (last axis is time).
    """
    lo = max(0.1, f_center - bandwidth / 2.0)
    hi = min(0.49 * sfreq, f_center + bandwidth / 2.0)
    if hi <= lo:
        raise ValueError(f"Invalid band [{lo}, {hi}] for sfreq={sfreq}")
    sos = butter(order, [lo / (sfreq / 2), hi / (sfreq / 2)], btype="band", output="sos")
    filtered = sosfiltfilt(sos, data, axis=-1)
    analytic = hilbert(filtered, axis=-1)
    amplitude = np.abs(analytic)
    phase = np.angle(analytic)
    return amplitude, phase


@dataclass
class EnvelopeResult:
    amplitude: np.ndarray  # (n_times,)
    phase: np.ndarray  # (n_times,)
    sfreq: float
    f_env: float
    bandwidth: float


def extract_ti_envelope(
    raw_data: np.ndarray,
    sfreq: float,
    f_env: float,
    bandwidth: float = 2.0,
) -> EnvelopeResult:
    """Extract the TI envelope (amplitude + instantaneous phase) from a reference signal.

    `raw_data` should be a 1D time series — either a stim-monitor channel or the mean
    of a set of channels known to directly record the TI beat.
    """
    if raw_data.ndim != 1:
        raise ValueError("extract_ti_envelope expects a 1D signal.")
    amp, phase = bandpass_hilbert(raw_data, sfreq=sfreq, f_center=f_env, bandwidth=bandwidth)
    log.info(
        "TI envelope @ %.2f Hz (bw=%.1f): mean amp = %.3e",
        f_env,
        bandwidth,
        float(amp.mean()),
    )
    return EnvelopeResult(amplitude=amp, phase=phase, sfreq=sfreq, f_env=f_env, bandwidth=bandwidth)
