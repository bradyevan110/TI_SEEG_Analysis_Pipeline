"""Tests for event->epochs conversion."""

from __future__ import annotations

from ti_seeg.events.epochs import (
    make_condition_epochs,
    make_sliding_epochs,
    select_condition_events,
)


def test_select_condition_events(synthetic_events) -> None:
    rows = select_condition_events(synthetic_events, "active_stim")
    assert len(rows) == 1
    assert rows["canonical"].iloc[0] == "active_stim"


def test_make_condition_epochs_builds_expected_counts(
    synthetic_raw, synthetic_events, minimal_config
):
    out = make_condition_epochs(synthetic_raw, synthetic_events, minimal_config)
    assert set(out) == {"baseline", "active_stim", "no_stim"}
    for cond, ep in out.items():
        assert len(ep) == 1, f"{cond}: expected 1 epoch, got {len(ep)}"


def test_make_sliding_epochs_nonempty(synthetic_raw, minimal_config):
    minimal_config.events.sliding.window_sec = 1.0
    minimal_config.events.sliding.overlap = 0.0
    epochs = make_sliding_epochs(synthetic_raw, minimal_config)
    # 4 s duration, 1 s window, step=1s => ~3 epochs (arange excludes endpoint).
    assert len(epochs) >= 2
