"""3D visualization helpers for TI E-field outputs.

The 3D mesh plot reads the portable ``.npz`` produced by
:func:`ti_seeg.source.efield.export_envelope_surface`, so this module does
not need SimNIBS importable. ``pyvista`` is an optional dependency
(``uv sync --extra efield``) — the function raises a clear ImportError
when missing.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..logging import get_logger

log = get_logger("visualization.efield_plots")


def plot_efield_orthoslice(
    envelope_nifti: Path,
    t1_bg: Path | None = None,
    threshold: float | None = None,
    title: str = "TI envelope",
) -> plt.Figure:
    """Three orthogonal slices through the envelope volume, optionally
    overlaid on a background T1. Uses nilearn (already a main dep)."""
    from nilearn import plotting

    fig = plt.figure(figsize=(12, 4))
    plotting.plot_stat_map(
        str(envelope_nifti),
        bg_img=str(t1_bg) if t1_bg and Path(t1_bg).exists() else None,
        threshold=threshold,
        title=title,
        figure=fig,
        display_mode="ortho",
        cmap="hot",
        colorbar=True,
    )
    return fig


def plot_efield_3d_mesh(
    surface_npz: Path,
    contacts_df: pd.DataFrame | None = None,
    title: str = "TI envelope (3D)",
    contact_radius_mm: float = 2.0,
) -> plt.Figure:
    """Off-screen pyvista render of the head surface colored by envelope
    magnitude, with SEEG contacts as spheres.

    Reads the .npz produced by ``export_envelope_surface`` (points, cells,
    scalars) — keeps SimNIBS out of the visualization process.
    """
    try:
        import pyvista as pv
    except ImportError as e:
        raise ImportError(
            "pyvista is required for 3D E-field plots. Install with `uv sync --extra efield`."
        ) from e

    if not Path(surface_npz).exists():
        raise FileNotFoundError(f"Surface npz not found: {surface_npz}")

    arr = np.load(str(surface_npz))
    points = arr["points"].astype(np.float64)
    cells = arr["cells"].astype(np.int64)
    scalars = arr["scalars"].astype(np.float64)

    # SimNIBS surface elements have 3 nodes (triangles).
    if cells.ndim != 2 or cells.shape[1] != 3:
        raise ValueError(f"Expected (N, 3) triangle cells, got shape {cells.shape}")
    cells_pv = np.hstack([np.full((cells.shape[0], 1), 3, dtype=np.int64), cells])
    cell_types = np.full(cells.shape[0], pv.CellType.TRIANGLE, dtype=np.uint8)
    grid = pv.UnstructuredGrid(cells_pv.ravel(), cell_types, points)
    grid["TI"] = scalars

    # Headless render. Setting OFF_SCREEN before instantiating the Plotter
    # keeps things robust on macOS / CI.
    pv.OFF_SCREEN = True
    os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

    plotter = pv.Plotter(off_screen=True, window_size=[1024, 768])
    plotter.add_mesh(grid, scalars="TI", cmap="hot", opacity=0.9, smooth_shading=True)

    if contacts_df is not None and {"x", "y", "z"}.issubset(contacts_df.columns):
        valid = contacts_df.dropna(subset=["x", "y", "z"])
        # Coerce to float; some BIDS rows have "n/a" strings.
        for col in ["x", "y", "z"]:
            valid = valid[pd.to_numeric(valid[col], errors="coerce").notna()]
        for _, c in valid.iterrows():
            plotter.add_mesh(
                pv.Sphere(
                    radius=contact_radius_mm,
                    center=(float(c["x"]), float(c["y"]), float(c["z"])),
                ),
                color="cyan",
                smooth_shading=True,
            )

    plotter.add_text(title, font_size=12)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        png_path = Path(f.name)
    try:
        plotter.screenshot(str(png_path), window_size=[1024, 768])
    finally:
        plotter.close()

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.imshow(plt.imread(png_path))
    ax.axis("off")
    fig.tight_layout()
    png_path.unlink(missing_ok=True)
    return fig


def plot_per_contact_envelope(
    per_contact: pd.DataFrame,
    roi_groups: dict[str, list[str]] | None = None,
    title: str = "Predicted TI envelope per contact",
) -> plt.Figure:
    """Bar chart of envelope_mean per contact, color-coded by ROI."""
    if per_contact.empty:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.text(0.5, 0.5, "No per-contact envelope data.", ha="center", va="center")
        ax.axis("off")
        return fig

    df = per_contact.copy().sort_values("envelope_mean", ascending=False)
    color_lookup: dict[str, tuple] = {}
    if roi_groups:
        palette = plt.cm.tab20(np.linspace(0, 1, max(1, len(roi_groups))))
        for (_roi, chans), col in zip(roi_groups.items(), palette, strict=False):
            for ch in chans:
                color_lookup[ch] = tuple(col)

    colors = [color_lookup.get(n, "#888888") for n in df["name"]]
    fig, ax = plt.subplots(figsize=(max(8, len(df) * 0.05), 4))
    names = df["name"].tolist()
    xs = np.arange(len(names))
    ax.bar(xs, df["envelope_mean"].to_numpy(), color=colors)
    ax.set_xticks(xs)
    ax.set_xticklabels(names, rotation=90, fontsize=5)
    ax.set_ylabel("E-field magnitude (V/m)")
    ax.set_title(title)
    fig.tight_layout()
    return fig


__all__ = [
    "plot_efield_3d_mesh",
    "plot_efield_orthoslice",
    "plot_per_contact_envelope",
]
