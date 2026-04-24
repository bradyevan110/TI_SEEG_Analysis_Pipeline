"""Tests for PLV-to-reference and surrogate significance."""

from __future__ import annotations

import numpy as np

from ti_seeg.phase.entrainment import plv_to_reference, plv_to_reference_with_surrogates


def test_plv_high_for_locked_channel_low_for_noise() -> None:
    rng = np.random.default_rng(0)
    sfreq = 1000.0
    n = 5000
    t = np.arange(n) / sfreq
    f = 10.0

    driven = np.sin(2 * np.pi * f * t)  # phase-locked to reference
    noise = rng.normal(size=n)

    data = np.stack([driven, noise])
    ch_names = ["driven", "noise"]

    # Reference phase = Hilbert phase of a 10 Hz sinusoid with offset.
    ref_phase = np.angle(
        np.exp(1j * (2 * np.pi * f * t + 0.3))
    )

    result = plv_to_reference(
        data=data,
        ch_names=ch_names,
        reference_phase=ref_phase,
        sfreq=sfreq,
        f_center=f,
        bandwidth=2.0,
    )
    assert result.plv[0] > 0.8
    assert result.plv[1] < 0.3


def test_surrogate_distinguishes_driven_from_noise() -> None:
    """Driven channel's PLV should clearly exceed the noise channel's, and its
    p-value (from time-shift surrogates) should be lower. Exact alpha thresholds
    are brittle with pure-sinusoid references (shift-invariant PLV), so we
    break periodicity with additive 1/f-ish noise and assert a margin."""
    rng = np.random.default_rng(1)
    sfreq = 1000.0
    n = 4000
    t = np.arange(n) / sfreq
    f = 8.0

    # Add broadband noise so time-shifted surrogates actually de-correlate.
    driven = np.sin(2 * np.pi * f * t + 0.5) + 0.6 * rng.normal(size=n)
    noise_ch = rng.normal(size=n)
    data = np.stack([driven, noise_ch])
    ref_phase = np.angle(np.exp(1j * 2 * np.pi * f * t))

    result = plv_to_reference_with_surrogates(
        data=data,
        ch_names=["driven", "noise"],
        reference_phase=ref_phase,
        sfreq=sfreq,
        f_center=f,
        bandwidth=2.0,
        n_surrogates=200,
        seed=42,
    )
    assert result.p_values is not None
    # Driven should have a much higher PLV and a noticeably lower p-value.
    assert result.plv[0] > result.plv[1] + 0.3
    assert result.p_values[0] < result.p_values[1]
