"""Preprocessing: filtering, bad-channel detection, re-referencing."""

from .artifacts import detect_bad_channels
from .filters import apply_bandpass, apply_notches, carrier_notch_freqs
from .referencing import apply_reference, bipolar_pairs_from_shanks, parse_shank

__all__ = [
    "apply_bandpass",
    "apply_notches",
    "apply_reference",
    "bipolar_pairs_from_shanks",
    "carrier_notch_freqs",
    "detect_bad_channels",
    "parse_shank",
]
