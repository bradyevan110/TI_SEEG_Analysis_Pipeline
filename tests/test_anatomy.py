"""Tests for ROI grouping and anatomical label lookup."""

from __future__ import annotations

import pandas as pd

from ti_seeg.anatomy.contacts import (
    anat_label_column,
    channel_to_anat_label,
    group_by_rois,
)
from ti_seeg.utils import match_roi


def test_anat_label_column_detected() -> None:
    df = pd.DataFrame({"name": ["A1"], "anatomical_label": ["Hippocampus"]})
    assert anat_label_column(df) == "anatomical_label"


def test_anat_label_column_recognizes_short_anat() -> None:
    # HANDOFF v2 §2 documents the column as "anat"; keep it a first-class candidate.
    df = pd.DataFrame({"name": ["A1"], "anat": ["Hippocampus"]})
    assert anat_label_column(df) == "anat"


def test_channel_to_anat_label_with_bipolar_fallback() -> None:
    df = pd.DataFrame(
        {
            "name": ["LAH1", "LAH2"],
            "anatomical_label": ["Left-Hippocampus", "Left-Hippocampus"],
        }
    )
    lookup = channel_to_anat_label(df, ["LAH1", "LAH2-LAH1"])
    assert lookup["LAH1"] == "Left-Hippocampus"
    assert lookup["LAH2-LAH1"] == "Left-Hippocampus"  # falls back to anode's label


def test_group_by_rois() -> None:
    df = pd.DataFrame(
        {
            "name": ["LAH1", "LAH2", "LAmy1"],
            "anatomical_label": ["Left-Hippocampus", "Left-Hippocampus", "Left-Amygdala"],
        }
    )
    rois = {"hippocampus": ["hippocampus"], "amygdala": ["amygdala"]}
    grouped = group_by_rois(df, ["LAH1", "LAH2", "LAmy1"], rois)
    assert grouped["hippocampus"] == ["LAH1", "LAH2"]
    assert grouped["amygdala"] == ["LAmy1"]


def test_match_roi_case_insensitive() -> None:
    assert match_roi("Right-Hippocampus", ["hippo"])
    assert not match_roi(None, ["hippo"])
