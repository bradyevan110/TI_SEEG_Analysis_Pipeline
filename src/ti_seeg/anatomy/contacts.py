"""Map SEEG contacts to anatomical ROIs using electrodes.tsv labels."""

from __future__ import annotations

import pandas as pd

from ..logging import get_logger
from ..utils import group_channels_by_roi

log = get_logger("anatomy.contacts")

# Common column names for anatomical labels in BIDS electrodes.tsv files.
_ANAT_COLUMN_CANDIDATES = [
    "anatomical_label",
    "anat_label",
    "region",
    "Region",
    "destrieux",
    "AAL",
    "aparc",
    "hemisphere_region",
    "label",
]


def anat_label_column(electrodes: pd.DataFrame) -> str | None:
    """Guess which column of electrodes.tsv holds anatomical labels."""
    for cand in _ANAT_COLUMN_CANDIDATES:
        if cand in electrodes.columns:
            return cand
    # Heuristic fallback: any string column with many unique values.
    for c in electrodes.columns:
        if electrodes[c].dtype == object and electrodes[c].nunique() >= 3 and c.lower() != "name":
            return c
    return None


def channel_to_anat_label(
    electrodes: pd.DataFrame,
    ch_names: list[str],
    label_col: str | None = None,
) -> dict[str, str | None]:
    """Return a {channel_name: anat_label} dict. Name column is assumed 'name'."""
    if "name" not in electrodes.columns:
        raise KeyError("electrodes.tsv missing required 'name' column.")
    label_col = label_col or anat_label_column(electrodes)
    if label_col is None:
        log.warning("No anatomical-label column found in electrodes.tsv.")
        return {ch: None for ch in ch_names}

    lookup = dict(
        zip(electrodes["name"].astype(str), electrodes[label_col].astype(str), strict=False)
    )

    out: dict[str, str | None] = {}
    for ch in ch_names:
        if ch in lookup:
            out[ch] = lookup[ch]
            continue
        # Try bipolar form "A-B": assign the anode's region.
        if "-" in ch:
            anode = ch.split("-", 1)[0]
            out[ch] = lookup.get(anode)
        else:
            out[ch] = None
    return out


def group_by_rois(
    electrodes: pd.DataFrame,
    ch_names: list[str],
    rois: dict[str, list[str]],
    label_col: str | None = None,
) -> dict[str, list[str]]:
    """Group channel names into the user-defined ROI buckets."""
    labels = channel_to_anat_label(electrodes, ch_names, label_col=label_col)
    return group_channels_by_roi(labels, rois)


def get_roi_channels(
    electrodes: pd.DataFrame,
    ch_names: list[str],
    rois: dict[str, list[str]],
    roi: str,
) -> list[str]:
    grouped = group_by_rois(electrodes, ch_names, rois)
    if roi not in grouped:
        raise KeyError(f"ROI {roi!r} not defined; known: {sorted(grouped)}")
    return grouped[roi]
