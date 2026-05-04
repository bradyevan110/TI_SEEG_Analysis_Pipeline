"""Shared pytest fixtures: synthetic TI-modulated SEEG data."""

from __future__ import annotations

import mne
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sfreq() -> float:
    # High enough to resolve 2 kHz carriers.
    return 8192.0


@pytest.fixture
def ti_params() -> dict[str, float]:
    # Excitation block by default: 5 Hz envelope.
    return {"f1_hz": 2000.0, "f2_hz": 2005.0, "envelope_hz": 5.0}


@pytest.fixture
def ch_names() -> list[str]:
    # Two shanks, 4 contacts each, formatted like real SEEG names.
    return [f"{pref}{i}" for pref in ("LAH", "RAM") for i in range(1, 5)]


@pytest.fixture
def synthetic_raw(
    sfreq: float, ti_params: dict[str, float], ch_names: list[str]
) -> mne.io.RawArray:
    """Synthetic SEEG-like Raw with one channel carrying a 5 Hz envelope-modulated 2 kHz carrier,
    plus noise channels."""
    rng = np.random.default_rng(42)
    duration = 4.0
    n_samples = int(duration * sfreq)
    t = np.arange(n_samples) / sfreq
    n_ch = len(ch_names)
    data = rng.normal(scale=5e-6, size=(n_ch, n_samples))  # noise ~5 uV

    # Inject TI signal on channel 0: sum of two carriers -> envelope beat at |f1-f2|.
    f1, f2 = ti_params["f1_hz"], ti_params["f2_hz"]
    ti_signal = 50e-6 * (np.cos(2 * np.pi * f1 * t) + np.cos(2 * np.pi * f2 * t))
    data[0] += ti_signal

    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="seeg")
    return mne.io.RawArray(data, info, verbose="WARNING")


@pytest.fixture
def synthetic_events(sfreq: float) -> pd.DataFrame:
    """Three condition epochs: baseline, active_stim, no_stim."""
    return pd.DataFrame(
        {
            "onset": [0.2, 1.2, 2.5],
            "duration": [0.0, 0.0, 0.0],
            "trial_type": ["baseline", "active_stim", "no_stim"],
            "canonical": ["baseline", "active_stim", "no_stim"],
        }
    )


@pytest.fixture
def minimal_config(tmp_path, ti_params):
    """Minimal PipelineConfig suitable for unit tests."""
    from ti_seeg.config import PipelineConfig, TIStimConfig

    cfg = PipelineConfig(
        subject="TEST",
        session="01",
        task="synthetic",
        run="01",
        bids_root=str(tmp_path / "bids"),
        derivatives_root=str(tmp_path / "derivatives"),
        ti=TIStimConfig(**ti_params),
        rois={"hippocampus": ["hippocampus", "LAH"]},
    )
    cfg.events.label_map = {
        "baseline": "baseline",
        "active_stim": "active_stim",
        "no_stim": "no_stim",
    }
    cfg.events.epoch_window = {
        "baseline": [0.0, 0.5],
        "active_stim": [-0.2, 0.8],
        "no_stim": [-0.2, 0.8],
    }
    cfg.spectral.fmax = 300.0
    cfg.tfr.fmin = 2.0
    cfg.tfr.fmax = 50.0
    cfg.tfr.n_freqs = 10
    return cfg
