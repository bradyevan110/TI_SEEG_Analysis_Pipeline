"""Spectral connectivity wrappers built on mne-connectivity."""

from __future__ import annotations

from dataclasses import dataclass

import mne
import numpy as np

from ..config import PipelineConfig
from ..logging import get_logger

log = get_logger("connectivity")


@dataclass
class ConnectivityResult:
    method: str
    band: str
    fmin: float
    fmax: float
    matrix: np.ndarray  # (n_channels, n_channels), symmetric (for coh/wPLI/PLV)
    ch_names: list[str]


def _method_alias(name: str) -> str:
    # mne-connectivity accepts 'coh', 'wpli', 'plv', 'imcoh', ...
    aliases = {"coherence": "coh", "wPLI": "wpli", "pli": "pli"}
    return aliases.get(name, name)


def compute_connectivity(
    epochs: mne.Epochs,
    config: PipelineConfig,
    methods: list[str] | None = None,
) -> list[ConnectivityResult]:
    from mne_connectivity import spectral_connectivity_epochs

    cfg = config.connectivity
    methods = methods or cfg.method
    results: list[ConnectivityResult] = []
    ch_names = epochs.ch_names

    for band_name, (lo, hi) in cfg.bands.items():
        log.info(
            "Connectivity band=%s [%.1f, %.1f], methods=%s",
            band_name,
            lo,
            hi,
            methods,
        )
        con = spectral_connectivity_epochs(
            epochs,
            method=[_method_alias(m) for m in methods],
            sfreq=epochs.info["sfreq"],
            fmin=lo,
            fmax=hi,
            faverage=True,
            mode="multitaper",
            mt_adaptive=False,
            verbose="WARNING",
        )
        if not isinstance(con, list):
            con = [con]
        for m, c in zip(methods, con, strict=False):
            # Data shape: (n_signals, n_signals, n_bands=1)
            mat = c.get_data(output="dense").squeeze(-1)
            # Mirror lower-triangular (mne-connectivity fills lower only).
            mat = mat + mat.T
            np.fill_diagonal(mat, 0.0)
            results.append(
                ConnectivityResult(
                    method=m,
                    band=band_name,
                    fmin=lo,
                    fmax=hi,
                    matrix=mat,
                    ch_names=list(ch_names),
                )
            )
    return results
