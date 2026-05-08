"""Project contact-level scalar results onto a volumetric T1, and stub for E-field.

True inverse modeling is not meaningful for intracranial SEEG — the electrodes
already sample the source. v1 therefore provides (a) visualization projection
of contact-level effect sizes onto a T1/fsaverage for inspection and (b) a
placeholder for TI E-field modeling (SimNIBS / ROAST) to be implemented in v2.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..logging import get_logger

log = get_logger("source.localization")


def project_contact_values_to_t1(
    electrodes: pd.DataFrame,
    values: dict[str, float],
    t1_path: str | Path | None = None,
    radius_mm: float = 4.0,
    out_path: str | Path | None = None,
) -> np.ndarray | None:
    """Build a 3D volume of per-voxel values using Gaussian-weighted contact contributions.

    If `t1_path` is provided, the output volume is co-aligned and saved as NIfTI.
    Otherwise returns the volume array without saving.

    Parameters
    ----------
    electrodes : DataFrame with columns 'name', 'x', 'y', 'z' in MRI coords (mm).
    values : {contact_name: scalar} mapping of the quantity to project.
    radius_mm : std-dev of Gaussian spread per contact.
    """
    required = {"name", "x", "y", "z"}
    if not required.issubset(set(electrodes.columns)):
        log.warning("electrodes.tsv missing x/y/z columns; skipping projection.")
        return None

    contacts = electrodes.set_index("name")
    matched = contacts.index.intersection(list(values.keys()))
    if matched.empty:
        log.warning("No overlap between `values` keys and electrodes.tsv names.")
        return None

    if t1_path is None:
        log.info("No T1 provided; building a bounding-box volume around contacts.")
        xs = contacts.loc[matched, ["x", "y", "z"]].to_numpy()
        lo = xs.min(axis=0) - 10.0
        hi = xs.max(axis=0) + 10.0
        spacing = 1.0  # 1 mm
        shape = np.ceil((hi - lo) / spacing).astype(int)
        grid = np.zeros(shape, dtype=np.float32)
        origin = lo
    else:
        import nibabel as nib  # lazy import

        img = nib.load(str(t1_path))
        shape = np.asarray(img.shape)
        grid = np.zeros(shape, dtype=np.float32)
        # Simplified: assume voxel = 1 mm, RAS-aligned affine. A robust
        # implementation would resample using img.affine.
        origin = np.zeros(3)

    for name in matched:
        x, y, z = contacts.loc[name, ["x", "y", "z"]].to_numpy(dtype=float)
        val = float(values[name])
        idx = np.round(np.array([x, y, z]) - origin).astype(int)
        # Gaussian kernel in a local box.
        r = int(np.ceil(3 * radius_mm))
        slices = tuple(
            slice(max(0, idx[d] - r), min(grid.shape[d], idx[d] + r + 1)) for d in range(3)
        )
        if any(s.stop <= s.start for s in slices):
            continue
        xx, yy, zz = np.meshgrid(
            np.arange(slices[0].start, slices[0].stop) - idx[0],
            np.arange(slices[1].start, slices[1].stop) - idx[1],
            np.arange(slices[2].start, slices[2].stop) - idx[2],
            indexing="ij",
        )
        weight = np.exp(-(xx**2 + yy**2 + zz**2) / (2 * radius_mm**2))
        grid[slices] += (val * weight).astype(np.float32)

    if out_path is not None and t1_path is not None:
        import nibabel as nib

        img = nib.load(str(t1_path))
        out_img = nib.Nifti1Image(grid, img.affine)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        nib.save(out_img, str(out_path))
        log.info("Wrote projected volume: %s", out_path)

    return grid


def compute_ti_field(*args, **kwargs) -> None:
    """Planned v2: TI E-field modeling via SimNIBS / ROAST integration."""
    raise NotImplementedError(
        "TI E-field modeling (SimNIBS/ROAST) is planned for v2 of the pipeline."
    )
