"""PLV-to-reference with surrogate significance testing."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..logging import get_logger
from .envelope import bandpass_hilbert

log = get_logger("phase.entrainment")


@dataclass
class PLVResult:
    plv: np.ndarray  # (n_channels,)
    ch_names: list[str]
    f_ref: float
    p_values: np.ndarray | None = None  # (n_channels,) from surrogate test


def _plv(phase_a: np.ndarray, phase_b: np.ndarray) -> np.ndarray:
    """PLV across the time axis for arrays of shape (n_channels, n_times)."""
    d = phase_a - phase_b
    return np.abs(np.mean(np.exp(1j * d), axis=-1))


def plv_to_reference(
    data: np.ndarray,  # (n_channels, n_times)
    ch_names: list[str],
    reference_phase: np.ndarray,  # (n_times,)
    sfreq: float,
    f_center: float,
    bandwidth: float = 2.0,
) -> PLVResult:
    """Phase-locking of each channel's narrowband phase at f_center to a reference."""
    _, ch_phase = bandpass_hilbert(data, sfreq=sfreq, f_center=f_center, bandwidth=bandwidth)
    # Broadcast reference to shape (n_channels, n_times).
    ref = np.broadcast_to(reference_phase, ch_phase.shape)
    plv = _plv(ch_phase, ref)
    log.info(
        "PLV @ %.2f Hz: mean=%.3f, max=%.3f, n_channels=%d",
        f_center,
        float(plv.mean()),
        float(plv.max()),
        len(ch_names),
    )
    return PLVResult(plv=plv, ch_names=ch_names, f_ref=f_center)


def plv_to_reference_with_surrogates(
    data: np.ndarray,
    ch_names: list[str],
    reference_phase: np.ndarray,
    sfreq: float,
    f_center: float,
    bandwidth: float = 2.0,
    n_surrogates: int = 200,
    seed: int = 0,
) -> PLVResult:
    """Same as plv_to_reference but adds per-channel p-values from time-shift surrogates."""
    result = plv_to_reference(
        data=data,
        ch_names=ch_names,
        reference_phase=reference_phase,
        sfreq=sfreq,
        f_center=f_center,
        bandwidth=bandwidth,
    )

    _, ch_phase = bandpass_hilbert(data, sfreq=sfreq, f_center=f_center, bandwidth=bandwidth)
    n_times = ch_phase.shape[-1]
    rng = np.random.default_rng(seed)
    # Avoid trivial shifts near 0 or full length.
    min_shift = int(0.1 * n_times)
    surrogate_plvs = np.empty((n_surrogates, len(ch_names)))
    for i in range(n_surrogates):
        shift = int(rng.integers(min_shift, n_times - min_shift))
        shifted_ref = np.roll(reference_phase, shift)
        ref_b = np.broadcast_to(shifted_ref, ch_phase.shape)
        surrogate_plvs[i] = _plv(ch_phase, ref_b)

    # One-sided p-value: fraction of surrogate PLVs >= observed.
    p = (surrogate_plvs >= result.plv[np.newaxis, :]).mean(axis=0)
    # Guard against zero p-values.
    p = np.clip(p, 1.0 / (n_surrogates + 1), 1.0)
    result.p_values = p
    log.info(
        "Surrogate PLV test: n_sig (p<0.05) = %d / %d",
        int((p < 0.05).sum()),
        len(ch_names),
    )
    return result
