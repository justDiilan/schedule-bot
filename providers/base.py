from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

@dataclass(frozen=True)
class Slot:
    start: str  # "01:00"
    end: str    # "06:30"
    kind: str   # e.g. "DEFINITE_OUTAGE" or other

@dataclass(frozen=True)
class DaySchedule:
    title: str               # e.g. "Вівторок, 10.12.2024 на 00:00"
    group_key: str           # e.g. "1.1"
    outages: List[Slot]      # list of outage intervals

@dataclass(frozen=True)
class RegionMeta:
    code: str                # internal code (e.g. "kiev")
    name: str                # "Київ"
    groups: List[str]        # e.g. ["1", "2", ...]
    subgroups: List[str]     # e.g. ["1", "2"] for ".1/.2"

class OutageProvider:
    """
    Provider must:
      - list regions
      - list groups/subgroups for region
      - return today/tomorrow schedule for a concrete group.subgroup
    """
    id: str  # "yasno" / "svitlo" etc.

    async def list_regions(self) -> List[RegionMeta]:
        raise NotImplementedError

    async def get_schedule(
        self, region_code: str, group: str, subgroup: str
    ) -> Tuple[Optional[DaySchedule], Optional[DaySchedule], int]:
        """
        Returns (today, tomorrow, last_update_unix).
        """
        raise NotImplementedError