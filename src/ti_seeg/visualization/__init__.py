"""Plotting + HTML reporting."""

from .efield_plots import (
    plot_efield_3d_mesh,
    plot_efield_orthoslice,
    plot_per_contact_envelope,
)
from .plots import (
    plot_bad_channels_qc,
    plot_connectivity_matrix,
    plot_contacts_on_brain,
    plot_psd,
    plot_tfr_roi,
)
from .report import build_report, save_figure

__all__ = [
    "build_report",
    "plot_bad_channels_qc",
    "plot_connectivity_matrix",
    "plot_contacts_on_brain",
    "plot_efield_3d_mesh",
    "plot_efield_orthoslice",
    "plot_per_contact_envelope",
    "plot_psd",
    "plot_tfr_roi",
    "save_figure",
]
