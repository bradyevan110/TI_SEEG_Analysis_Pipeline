"""Tests for notch/bandpass filters and carrier-notch frequency generation."""

from __future__ import annotations

import numpy as np

from ti_seeg.preprocessing.filters import apply_notches, carrier_notch_freqs


def test_carrier_notch_freqs_includes_sum_and_harmonics(minimal_config) -> None:
    nyq = 4000.0
    freqs = carrier_notch_freqs(
        minimal_config.ti,
        nyquist=nyq,
        n_harmonics=minimal_config.preprocessing.carrier_harmonics,
    )
    # f1 and f2 present
    assert 2000.0 in freqs
    assert 2005.0 in freqs
    # f1+f2 is above nyquist 4000, so should NOT be present
    assert not any(f > nyq for f in freqs)


def test_notch_attenuates_injected_carrier(synthetic_raw, minimal_config) -> None:
    # Measure power at 2 kHz before vs after notching.
    raw = synthetic_raw.copy()
    data_before = raw.get_data()[0]
    power_before = np.mean(data_before**2)

    apply_notches(raw, minimal_config)
    data_after = raw.get_data()[0]
    power_after = np.mean(data_after**2)

    # Most of channel 0's power was the carrier; notching should drop it substantially.
    assert power_after < 0.5 * power_before
