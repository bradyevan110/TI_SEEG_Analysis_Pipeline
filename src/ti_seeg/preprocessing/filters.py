"""Filtering: line-noise / carrier / harmonic notches and bandpass."""

from __future__ import annotations

from collections.abc import Iterable

import mne
import numpy as np

from ..config import PipelineConfig, PreprocessingConfig, TIStimConfig
from ..logging import get_logger

log = get_logger("preprocessing.filters")


def _harmonics(base: float, n: int, nyquist: float) -> list[float]:
    return [base * k for k in range(1, n + 1) if base * k < nyquist]


def carrier_notch_freqs(ti: TIStimConfig, nyquist: float, n_harmonics: int) -> list[float]:
    """Frequencies to notch: each carrier + harmonics, plus their sum (f1+f2)."""
    freqs: set[float] = set()
    for carrier in ti.carriers:
        freqs.update(_harmonics(carrier, n_harmonics, nyquist))
    sum_freq = ti.f1_hz + ti.f2_hz
    freqs.update(_harmonics(sum_freq, n_harmonics, nyquist))
    # Envelope itself should NOT be notched (we want to preserve it).
    return sorted(f for f in freqs if 0 < f < nyquist)


def apply_notches(
    raw: mne.io.BaseRaw,
    config: PipelineConfig,
) -> mne.io.BaseRaw:
    """Apply line-noise and TI-carrier notches in place and return raw.

    Uses MNE's zero-phase FIR notch by default (conservative).
    """
    pre: PreprocessingConfig = config.preprocessing
    ti: TIStimConfig = config.ti
    nyq = raw.info["sfreq"] / 2.0

    line_freqs = _harmonics(pre.line_freq, pre.line_harmonics, nyq)
    carrier_freqs = carrier_notch_freqs(ti, nyq, pre.carrier_harmonics)

    all_freqs = sorted(set(line_freqs + carrier_freqs))
    if not all_freqs:
        log.info("No notch frequencies below Nyquist — skipping.")
        return raw

    log.info(
        "Notch filtering (n=%d): line=%s, carriers+harmonics=%s",
        len(all_freqs),
        [round(f, 2) for f in line_freqs],
        [round(f, 2) for f in carrier_freqs],
    )
    raw.notch_filter(
        freqs=np.asarray(all_freqs),
        notch_widths=pre.notch_width_hz,
        method="fir",
        phase="zero",
        verbose="WARNING",
    )
    return raw


def apply_bandpass(
    raw: mne.io.BaseRaw,
    config: PipelineConfig,
) -> mne.io.BaseRaw:
    """Apply a broadband bandpass (default: 0.5 Hz HP, LP disabled / near Nyquist)."""
    bp: Iterable[float | None] = config.preprocessing.bandpass
    hp, lp = (list(bp) + [None, None])[:2]
    nyq = raw.info["sfreq"] / 2.0
    if lp is None or lp <= 0:
        # leave low-pass effectively off (MNE requires a value below nyquist).
        lp = 0.45 * raw.info["sfreq"]
    if hp is None or hp <= 0:
        hp = None  # means "no high-pass"
    log.info("Bandpass: hp=%s Hz, lp=%s Hz (nyq=%.1f)", hp, lp, nyq)
    raw.filter(
        l_freq=hp,
        h_freq=lp,
        method="fir",
        phase="zero",
        fir_design="firwin",
        verbose="WARNING",
    )
    return raw
