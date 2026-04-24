"""Tests for shank parsing + bipolar-pair generation."""

from __future__ import annotations

from ti_seeg.preprocessing.referencing import bipolar_pairs_from_shanks, parse_shank


def test_parse_shank_simple() -> None:
    assert parse_shank("LAH1") == ("LAH", 1)
    assert parse_shank("RAmy12") == ("RAmy", 12)
    assert parse_shank("LAH01") == ("LAH", 1)


def test_parse_shank_invalid() -> None:
    assert parse_shank("NoDigits") is None
    assert parse_shank("") is None


def test_bipolar_pairs_adjacent_only() -> None:
    names = ["LAH1", "LAH2", "LAH3", "LAH5", "RAM1", "RAM2"]
    pairs = bipolar_pairs_from_shanks(names)
    # LAH1-2, LAH2-3 (LAH3 to LAH5 is NOT adjacent), RAM1-2 => 3 pairs.
    pair_names = {tuple(sorted(p)) for p in pairs}
    assert ("LAH1", "LAH2") in pair_names
    assert ("LAH2", "LAH3") in pair_names
    assert ("RAM1", "RAM2") in pair_names
    assert len(pairs) == 3
