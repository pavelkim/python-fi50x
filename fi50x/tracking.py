"""
Tag presence tracking — turn successive inventory snapshots into new/lost events.

An inventory sweep is a point-in-time snapshot; consumers usually care about
*changes*: which tags just appeared and which just left the field. RF reads are
also flaky, so a tag may be missed for a sweep or two while still physically
present. :class:`TagTracker` debounces that with a configurable miss tolerance.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass
class TrackerDelta:
    """The change between the previous tracker state and the latest sweep."""

    new: List[str]      # EPCs that appeared this sweep
    lost: List[str]     # EPCs that dropped out (missed beyond the tolerance)
    present: List[str]  # EPCs currently considered in the field

    def has_changes(self) -> bool:
        return bool(self.new or self.lost)


class TagTracker:
    """
    Diff successive sets of EPCs to detect newly-seen and newly-lost tags.

    Args:
        miss_tolerance: how many consecutive sweeps a tag may be absent before it
            is declared lost. ``0`` reports a tag lost the first sweep it is
            missing; higher values smooth over flaky reads.
    """

    def __init__(self, miss_tolerance: int = 2) -> None:
        if miss_tolerance < 0:
            raise ValueError("miss_tolerance must be >= 0")
        self.miss_tolerance = miss_tolerance
        # epc -> consecutive misses (0 means seen on the latest sweep)
        self._misses: Dict[str, int] = {}

    def update(self, current: Iterable[str]) -> TrackerDelta:
        """Feed the EPCs seen on the latest sweep and get the resulting delta."""
        current_set = set(current)

        # A tag is "new" only if we are not already tracking it (a tag missing but
        # still within tolerance stays tracked, so its reappearance is not "new").
        new = sorted(epc for epc in current_set if epc not in self._misses)
        for epc in current_set:
            self._misses[epc] = 0

        lost = []
        for epc in list(self._misses):
            if epc in current_set:
                continue
            self._misses[epc] += 1
            if self._misses[epc] > self.miss_tolerance:
                lost.append(epc)
                del self._misses[epc]

        return TrackerDelta(
            new=new,
            lost=sorted(lost),
            present=sorted(self._misses),
        )

    def reset(self) -> None:
        """Forget all tracked tags."""
        self._misses.clear()
