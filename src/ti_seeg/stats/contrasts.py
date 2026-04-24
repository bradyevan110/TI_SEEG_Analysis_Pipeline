"""Cluster-permutation wrappers for TFR and PSD contrasts between conditions."""

from __future__ import annotations

from dataclasses import dataclass

import mne
import numpy as np
from mne.stats import permutation_cluster_test

from ..config import PipelineConfig
from ..logging import get_logger

log = get_logger("stats.contrasts")


@dataclass
class ClusterTestResult:
    T_obs: np.ndarray
    clusters: list
    cluster_p_values: np.ndarray
    H0: np.ndarray


def cluster_permutation_tfr(
    X: list[np.ndarray],
    config: PipelineConfig,
    tail: int | None = None,
) -> ClusterTestResult:
    """Run cluster-permutation test across conditions on TFR-like data.

    `X` is a list of arrays, one per condition, each shape (n_observations, ...).
    For a TFR contrast, observations = epochs, and remaining dims are
    (freqs, times) after picking one channel, or (n_channels, freqs, times)
    with a `connectivity` argument from MNE.
    """
    cfg = config.stats
    tail = cfg.tail if tail is None else tail
    T_obs, clusters, p, H0 = permutation_cluster_test(
        X,
        n_permutations=cfg.n_permutations,
        tail=tail,
        threshold=None,
        out_type="mask",
        verbose="WARNING",
    )
    n_sig = int((p < cfg.cluster_alpha).sum())
    log.info(
        "Cluster test: n_clusters=%d, n_sig @ alpha=%.2f: %d",
        len(clusters),
        cfg.cluster_alpha,
        n_sig,
    )
    return ClusterTestResult(T_obs=T_obs, clusters=list(clusters), cluster_p_values=p, H0=H0)


def paired_condition_tfr_contrast(
    epochs_a: mne.Epochs,
    epochs_b: mne.Epochs,
    config: PipelineConfig,
    pick: str | int = 0,
) -> ClusterTestResult:
    """Run a 2-condition cluster test on single-channel TFR power.

    Computes TFR per-epoch (not averaged) via Morlet.
    """
    from mne.time_frequency import tfr_morlet

    freqs = np.logspace(np.log10(config.tfr.fmin), np.log10(config.tfr.fmax), config.tfr.n_freqs)
    n_cycles = freqs / 2.0

    def _tfr_per_epoch(ep: mne.Epochs) -> np.ndarray:
        ep = ep.copy().pick([pick] if isinstance(pick, str) else pick)
        tfr = tfr_morlet(
            ep,
            freqs=freqs,
            n_cycles=n_cycles,
            average=False,
            return_itc=False,
            verbose="WARNING",
        )
        return tfr.data.squeeze(1)  # -> (n_epochs, n_freqs, n_times)

    Xa = _tfr_per_epoch(epochs_a)
    Xb = _tfr_per_epoch(epochs_b)
    return cluster_permutation_tfr([Xa, Xb], config=config)
