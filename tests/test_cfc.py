"""Test Tort modulation index recovers coupling from a synthetic signal."""

from __future__ import annotations

import numpy as np

from ti_seeg.phase.cfc import cfc_tort_mi


def test_tort_mi_detects_coupling() -> None:
    rng = np.random.default_rng(0)
    sfreq = 1000.0
    duration = 30.0
    n = int(sfreq * duration)
    t = np.arange(n) / sfreq

    theta = np.sin(2 * np.pi * 6 * t)
    gamma_amp = 1.0 + 0.7 * (theta > 0)  # amplitude gated on theta phase
    gamma = gamma_amp * np.sin(2 * np.pi * 80 * t)
    coupled = theta + 0.5 * gamma + 0.05 * rng.normal(size=n)

    mi_coupled, _ = cfc_tort_mi(
        coupled, sfreq=sfreq, phase_band=(4, 8), amp_band=(60, 100), n_bins=18
    )

    # Control: phase randomized gamma (no phase–amp coupling).
    gamma_ctrl = np.sin(2 * np.pi * 80 * t + rng.uniform(-np.pi, np.pi))
    uncoupled = theta + 0.5 * gamma_ctrl + 0.05 * rng.normal(size=n)
    mi_uncoupled, _ = cfc_tort_mi(
        uncoupled, sfreq=sfreq, phase_band=(4, 8), amp_band=(60, 100), n_bins=18
    )

    assert mi_coupled > mi_uncoupled
