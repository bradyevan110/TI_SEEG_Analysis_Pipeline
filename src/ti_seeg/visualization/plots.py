"""Standalone plotting helpers. Plots return matplotlib Figure objects."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..logging import get_logger

log = get_logger("visualization.plots")


def plot_bad_channels_qc(
    bad_channels: list[str],
    total_channels: int,
) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(4, 3))
    good = total_channels - len(bad_channels)
    ax.bar(["good", "bad"], [good, len(bad_channels)], color=["#4c72b0", "#c44e52"])
    ax.set_ylabel("channel count")
    ax.set_title("Bad-channel QC")
    for i, v in enumerate([good, len(bad_channels)]):
        ax.text(i, v, str(v), ha="center", va="bottom")
    fig.tight_layout()
    return fig


def plot_psd(
    freqs: np.ndarray,
    psd: np.ndarray,  # shape (n_channels, n_freqs) in V^2/Hz
    channel_names: list[str] | None = None,
    title: str = "PSD",
    fmax: float | None = None,
) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(8, 4))
    if fmax is None:
        fmax = float(freqs.max())
    mask = freqs <= fmax
    psd_db = 10 * np.log10(psd[:, mask] + 1e-30)
    ax.plot(freqs[mask], psd_db.T, linewidth=0.6, alpha=0.4)
    # Mean + 95% CI band.
    mean = psd_db.mean(axis=0)
    std = psd_db.std(axis=0)
    ax.plot(freqs[mask], mean, color="black", linewidth=1.5, label="mean")
    ax.fill_between(freqs[mask], mean - std, mean + std, alpha=0.2, color="black")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Power (dB)")
    ax.set_title(title)
    ax.legend(loc="upper right")
    fig.tight_layout()
    return fig


def plot_tfr_roi(
    tfr_data: np.ndarray,  # shape (n_freqs, n_times)
    freqs: np.ndarray,
    times: np.ndarray,
    title: str = "TFR",
    cmap: str = "RdBu_r",
    vlim: tuple[float, float] | None = None,
) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(7, 4))
    if vlim is None:
        v = np.abs(tfr_data).max()
        vlim = (-v, v)
    im = ax.pcolormesh(
        times, freqs, tfr_data, shading="auto", cmap=cmap, vmin=vlim[0], vmax=vlim[1]
    )
    ax.set_yscale("log")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Frequency (Hz)")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, label="power (log ratio)")
    fig.tight_layout()
    return fig


def plot_connectivity_matrix(
    matrix: np.ndarray,
    labels: list[str],
    title: str = "Connectivity",
    cmap: str = "viridis",
) -> plt.Figure:
    n = len(labels)
    fig, ax = plt.subplots(figsize=(max(6, n * 0.25), max(5, n * 0.25)))
    im = ax.imshow(matrix, cmap=cmap, aspect="equal")
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels, rotation=90, fontsize=7)
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_title(title)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    return fig


def plot_contacts_on_brain(
    electrodes: pd.DataFrame,
    highlight: list[str] | None = None,
    title: str = "Contacts",
    out_path: Path | None = None,
) -> plt.Figure | None:
    """Simple 2D glass-brain-style scatter in MRI coords (x,y,z).

    Not as pretty as nilearn/pyvista 3D but always works without a GL context.
    """
    required = {"name", "x", "y", "z"}
    if not required.issubset(set(electrodes.columns)):
        log.warning("electrodes.tsv missing x/y/z columns; cannot plot contacts.")
        return None

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    views = [("Sagittal", "y", "z"), ("Coronal", "x", "z"), ("Axial", "x", "y")]
    highlight_set = set(highlight or [])
    for ax, (title_v, a, b) in zip(axes, views, strict=False):
        ax.scatter(
            electrodes[a],
            electrodes[b],
            s=8,
            c=["#c44e52" if n in highlight_set else "#4c72b0" for n in electrodes["name"]],
            alpha=0.8,
        )
        ax.set_title(title_v)
        ax.set_xlabel(a)
        ax.set_ylabel(b)
        ax.set_aspect("equal", adjustable="datalim")
    fig.suptitle(title)
    fig.tight_layout()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=120)
    return fig
