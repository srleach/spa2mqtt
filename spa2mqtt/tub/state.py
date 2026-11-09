"""Current decoded values with change detection."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ..definitions.model import FieldValue


@dataclass
class TubState:
    clock: Callable[[], float] = time.monotonic
    values: dict[str, FieldValue] = field(default_factory=dict)
    changed_at: dict[str, float] = field(default_factory=dict)
    status_frames: int = 0
    last_status_at: float | None = None

    def update(self, new: Mapping[str, FieldValue]) -> dict[str, FieldValue]:
        """Apply a decoded status frame; return only the fields whose value changed."""
        self.status_frames += 1
        self.last_status_at = self.clock()
        return self._apply(new)

    def merge(self, new: Mapping[str, FieldValue]) -> dict[str, FieldValue]:
        """Apply values from a frame that is not the status frame (the counters stay put)."""
        return self._apply(new)

    def _apply(self, new: Mapping[str, FieldValue]) -> dict[str, FieldValue]:
        now = self.clock()
        changed: dict[str, FieldValue] = {}
        for key, value in new.items():
            if key not in self.values or self.values[key] != value:
                self.values[key] = value
                self.changed_at[key] = now
                changed[key] = value
        return changed
