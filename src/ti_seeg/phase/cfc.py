"""Cross-frequency coupling — Tort modulation index (phase–amplitude)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..logging import get_logger
from .envelope import bandpass_hilbert

log = get_logger("phase.cfc")


@dataclass
class CFCResult:
    mi: np.ndarray  # (n_channels, n_amp_bands)
    ch_names: list[str]
    phase_band: tuple[float, float]
    amp_bands: list[tuple[float, float]]
    distribution: np.ndarray | None = None  # (n_channels, n_amp_bands, n_bins)


def _tort_mi(phase: np.ndarray, amplitude: np.ndarray, n_bins: int = 18) -> tuple[float, np.ndarray]:
    """Tort 2010 modulation index for a single (phase, amplitude) pair, each shape (n_times,)."""
    bins = np.linspace(-np.pi, np.pi, n_bins + 1)
    bin_idx = np.digitize(phase, bins) - 1
    bin_idx = np.clip(bin_idx, 0, n_bins - 1)
    mean_amps = np.zeros(n_bins)
    for b in range(n_bins):
        mask = bin_idx == b
        mean_amps[b] = amplitude[mask].mean() if mask.any() else 0.0
    total = mean_amps.sum()
    if total <= 0:
        return 0.0, mean_amps
    p = mean_amps / total
    p_safe = np.where(p > 0, p, 1e-12)
    h = -np.sum(p_safe * np.log(p_safe))
    h_max = np.log(n_bins)
    mi = (h_max - h) / h_max
    return float(mi), p


def cfc_tort_mi(
    signal: np.ndarray,
    sfreq: float,
    phase_band: tuple[float, float],
    amp_band: tuple[float, float],
    n_bins: int = 18,
) -> tuple[float, np.ndarray]:
    """Compute Tort MI for a single channel signal."""
    ph_center = 0.5 * sum(phase_band)
    ph_bw = phase_band[1] - phase_band[0]
    am_center = 0.5 * sum(amp_band)
    am_bw = amp_band[1] - amp_band[0]
    _, phase = bandpass_hilbert(signal, sfreq=sfreq, f_center=ph_center, bandwidth=ph_bw)
    amplitude, _ = bandpass_hilbert(signal, sfreq=sfreq, f_center=am_center, bandwidth=am_bw)
    return _tort_mi(phase, amplitude, n_bins=n_bins)


def cfc_tort_mi_all(
    data: np.ndarray,  # (n_channels, n_times)
    ch_names: list[str],
    sfreq: float,
    phase_band: tuple[float, float],
    amp_bands: list[tuple[float, float]],
    n_bins: int = 18,
) -> CFCResult:
    n_ch = data.shape[0]
    n_amp = len(amp_bands)
    mi = np.zeros((n_ch, n_amp))
    dist = np.zeros((n_ch, n_amp, n_bins))
    for j, amp_band in enumerate(amp_bands):
        for i in range(n_ch):
            mi_ij, p_ij = cfc_tort_mi(
                data[i],
                sfreq=sfreq,
                phase_band=phase_band,
                amp_band=amp_band,
                n_bins=n_bins,
            )
            mi[i, j] = mi_ij
            dist[i, j] = p_ij
    log.info(
        "CFC Tort MI: phase=%s, amp bands=%s, mean MI per band = %s",
        phase_band,
        amp_bands,
        [float(mi[:, j].mean()) for j in range(n_amp)],
    )
    return CFCResult(
        mi=mi,
        ch_names=ch_names,
        phase_band=phase_band,
        amp_bands=amp_bands,
        distribution=dist,
    )
