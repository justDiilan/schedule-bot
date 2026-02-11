from __future__ import annotations
import aiohttp
import json
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
import os

from .base import OutageProvider, RegionMeta, DaySchedule, Slot

class TernopilProvider(OutageProvider):
    id = "ternopil"
    API_URL = "https://api-poweron.toe.com.ua/api/a_gpv_g"

    async def _fetch(self, params: dict) -> dict:
        async with aiohttp.ClientSession() as s:
            async with s.get(self.API_URL, params=params) as r:
                r.raise_for_status()
                return await r.json()

    def _slots_from_times(self, times: dict) -> List[Slot]:
        """
        API Values:
        0 - ON (Light)
        1 - OFF (Outage)
        10 - Switching/Possible Outage (Maybe)
        """
        # Sort times just in case
        sorted_keys = sorted(times.keys())
        
        slots = []
        if not sorted_keys:
            return slots

        def get_state(val_str):
            try:
                v = int(val_str)
                if v == 1: return "outage"
                if v == 10: return "switching"
                return "on"
            except ValueError:
                return "on"

        prev_state = get_state(times[sorted_keys[0]])
        start_time = sorted_keys[0]

        for t in sorted_keys:
            val = times[t]
            current_state = get_state(val)

            if current_state != prev_state:
                # Close previous interval if it was outage or switching
                if prev_state in ("outage", "switching"):
                    slots.append(Slot(start=start_time, end=t, kind=prev_state))
                
                start_time = t
                prev_state = current_state
        
        # Close last interval
        if prev_state in ("outage", "switching"):
             slots.append(Slot(start=start_time, end="24:00", kind=prev_state))

        return slots

    async def list_regions(self) -> List[RegionMeta]:
        return [RegionMeta(
            code="ternopil",
            name="Тернопільська обл.",
            groups=["1", "2", "3", "4", "5", "6"],
            subgroups=["1", "2"]
        )]

    async def get_schedule(
        self,
        region_code: str,
        group: str,
        subgroup: str
    ) -> Tuple[Optional[DaySchedule], Optional[DaySchedule], int]:
        
        import pytz
        from urllib.parse import quote
        
        tz = pytz.timezone("Europe/Kyiv")
        now = datetime.now(tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = (today_start + timedelta(days=2)) # Covers today and tomorrow effectively
        
        # Format dates as ISO 8601 with offset, urlencoded? 
        # aiohttp handles params encoding.
        # API expects: before=2026-02-12T00:00:00+00:00 ...
        # Let's ensure we send correct ISO format.
        # User example: 2026-02-12T00:00:00+00:00. This looks like UTC or just offset.
        # Let's try sending standard ISO.
        
        params = {
            "after": today_start.isoformat(),
            "before": tomorrow_end.isoformat(),
            "group[]": f"{group}.{subgroup}",
            "time": int(now.timestamp()) # Cache buster
        }

        try:
            data = await self._fetch(params)
            members = data.get("hydra:member", [])
        except Exception as e:
            print(f"Ternopil API fetch error: {e}")
            return None, None, 0

        today_str = now.strftime("%Y-%m-%d")
        tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")

        today_sched = None
        tomorrow_sched = None

        target_key = f"{group}.{subgroup}"

        for graph in members:
            # dateGraph: "2026-01-28T00:00:00+00:00"
            raw_date = graph.get("dateGraph", "")
            if not raw_date:
                continue
            
            # extract YYYY-MM-DD
            date_part = raw_date.split("T")[0]
            
            data_json = graph.get("dataJson", {})
            
            # dataJson might contain the key directly
            if target_key not in data_json:
                continue
            
            # dataJson[target_key] might be the dict with "times" or just the dict?
            # User example: "dataJson":{"3.1":{"times":{...}}}
            group_data = data_json[target_key]
            if "times" not in group_data:
                continue
                
            times = group_data["times"]
            slots = self._slots_from_times(times)
            
            # Simple title
            title = f"Графік на {date_part}" 
            
            ds = DaySchedule(
                title=title,
                date=date_part,
                group_key=target_key,
                outages=slots
            )

            if date_part == today_str:
                today_sched = ds
            elif date_part == tomorrow_str:
                tomorrow_sched = ds
        
        return today_sched, tomorrow_sched, 0
