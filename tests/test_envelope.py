"""Tests for envelope extraction and bandpass-Hilbert utilities."""

from __future__ import annotations

import numpy as np

from ti_seeg.phase.envelope import bandpass_hilbert, extract_ti_envelope


def test_envelope_recovers_direct_reference_signal() -> None:
    """`extract_ti_envelope` is documented for signals that directly contain f_env
    (e.g., a stim-monitor channel). Test with such a signal."""
    sfreq = 2000.0
    duration = 10.0
    n = int(sfreq * duration)
    t = np.arange(n) / sfreq
    f_env = 5.0

    signal = np.sin(2 * np.pi * f_env * t) + 0.05 * np.random.default_rng(0).normal(size=n)

    result = extract_ti_envelope(signal, sfreq=sfreq, f_env=f_env, bandwidth=2.0)
    # Phase should advance at 2π·f_env rad/s. Diff mean ≈ 2π·f_env/sfreq.
    unwrapped = np.unwrap(result.phase)
    # Trim filter edge effects.
    slope = (unwrapped[-500] - unwrapped[500]) / ((len(unwrapped) - 1000) / sfreq)
    est_f = slope / (2 * np.pi)
    assert abs(est_f - f_env) < 0.5


def test_bandpass_hilbert_2d_input() -> None:
    sfreq = 1000.0
    # Need enough samples for a 2 Hz-wide bandpass filter to have valid response.
    duration = 8.0
    n = int(sfreq * duration)
    t = np.arange(n) / sfreq
    sig = np.stack(
        [np.sin(2 * np.pi * 10 * t), np.sin(2 * np.pi * 10 * t + np.pi / 2)]
    )
    amp, phase = bandpass_hilbert(sig, sfreq=sfreq, f_center=10.0, bandwidth=2.0)
    assert amp.shape == sig.shape
    assert phase.shape == sig.shape
    # Mean envelope of a pure sinusoid should be ~1 after filter settles (trim edges).
    inner = amp[:, 1000:-1000]
    assert 0.7 < inner.mean() < 1.2
