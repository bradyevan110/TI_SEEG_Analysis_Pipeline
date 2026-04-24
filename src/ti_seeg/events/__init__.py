"""Event parsing + epoching."""

from .epochs import (
    make_condition_epochs,
    make_sliding_epochs,
    select_condition_events,
)

__all__ = [
    "make_condition_epochs",
    "make_sliding_epochs",
    "select_condition_events",
]
