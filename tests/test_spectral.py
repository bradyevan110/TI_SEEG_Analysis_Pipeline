"""Tests for PSD computation and band aggregation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ti_seeg.spectral.psd import PSDResult, aggregate_bands, contrast_psds


def _fake_psd_result(condition: str, peak_freq: float) -> PSDResult:
    freqs = np.linspace(1, 100, 200)
    # Channel 0 has a peak at peak_freq, channel 1 is flat.
    psd = np.ones((2, freqs.size))
    psd[0] += 5 * np.exp(-0.5 * ((freqs - peak_freq) / 2.0) ** 2)
    return PSDResult(freqs=freqs, psd=psd, ch_names=["ch0", "ch1"], condition=condition)


def test_aggregate_bands_returns_tidy_frame() -> None:
    res = _fake_psd_result("active_stim", peak_freq=10.0)
    df = aggregate_bands(res, {"alpha": [8, 13], "beta": [13, 30]})
    assert isinstance(df, pd.DataFrame)
    assert set(df["band"]) == {"alpha", "beta"}
    # ch0 alpha power should exceed beta power (because peak is at 10 Hz).
    ch0 = df[df["channel"] == "ch0"]
    alpha_power = float(ch0[ch0["band"] == "alpha"]["power"].iloc[0])
    beta_power = float(ch0[ch0["band"] == "beta"]["power"].iloc[0])
    assert alpha_power > beta_power


def test_contrast_psds_log_ratio_sign() -> None:
    a = _fake_psd_result("active_stim", peak_freq=10.0)
    b = _fake_psd_result("no_stim", peak_freq=40.0)
    ratio = contrast_psds(a, b)
    # ch0 @ 10 Hz should be positive (a > b); @ 40 Hz should be negative.
    ch0 = ratio.loc["ch0"]
    near_10 = ch0.iloc[np.argmin(np.abs(a.freqs - 10))]
    near_40 = ch0.iloc[np.argmin(np.abs(a.freqs - 40))]
    assert near_10 > 0
    assert near_40 < 0
