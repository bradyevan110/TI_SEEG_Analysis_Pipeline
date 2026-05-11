"""Re-referencing: bipolar-on-shank, common-average, monopolar pass-through."""

from __future__ import annotations

import re

import mne

from ..config import PipelineConfig
from ..logging import get_logger

log = get_logger("preprocessing.referencing")

# Match names like 'LAH1', 'LAH01', 'RAmy12', etc. Shank = letter prefix, idx = trailing int.
_NAME_RE = re.compile(r"^([A-Za-z'`]+)\s*-?\s*0*([0-9]+)$")


def parse_shank(name: str) -> tuple[str, int] | None:
    """Return (shank_prefix, contact_number) or None if unparseable."""
    m = _NAME_RE.match(name.strip())
    if not m:
        return None
    return m.group(1), int(m.group(2))


def bipolar_pairs_from_shanks(ch_names: list[str]) -> list[tuple[str, str]]:
    """Form adjacent-contact bipolar pairs within each shank.

    Contacts on the same shank with consecutive numbers are paired (k, k+1).
    """
    by_shank: dict[str, list[tuple[int, str]]] = {}
    for ch in ch_names:
        parsed = parse_shank(ch)
        if parsed is None:
            continue
        shank, idx = parsed
        by_shank.setdefault(shank, []).append((idx, ch))

    pairs: list[tuple[str, str]] = []
    for _shank, entries in by_shank.items():
        entries.sort()
        for (idx_a, name_a), (idx_b, name_b) in zip(entries[:-1], entries[1:], strict=False):
            if idx_b == idx_a + 1:
                pairs.append((name_b, name_a))  # anode=deeper, cathode=shallower
    return pairs


def apply_reference(
    raw: mne.io.BaseRaw,
    config: PipelineConfig,
) -> mne.io.BaseRaw:
    """Apply the configured reference scheme. Returns a new Raw."""
    scheme = config.preprocessing.reference
    if scheme == "monopolar":
        log.info("Reference: monopolar (no rereference applied).")
        return raw

    if scheme == "car":
        log.info("Reference: common-average.")
        raw_ref, _ = mne.set_eeg_reference(raw, ref_channels="average", verbose="WARNING")
        return raw_ref

    if scheme == "bipolar":
        pairs = bipolar_pairs_from_shanks(raw.ch_names)
        if not pairs:
            log.warning("No bipolar pairs parsed from channel names; falling back to monopolar.")
            return raw
        anodes = [a for a, _ in pairs]
        cathodes = [c for _, c in pairs]
        new_names = [f"{a}-{c}" for a, c in pairs]
        log.info("Reference: bipolar on-shank (%d derivations).", len(pairs))
        raw_bip = mne.set_bipolar_reference(
            raw,
            anode=anodes,
            cathode=cathodes,
            ch_name=new_names,
            drop_refs=True,
            verbose="WARNING",
        )
        return raw_bip

    raise ValueError(f"Unknown reference scheme: {scheme!r}")
