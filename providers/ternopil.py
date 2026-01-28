from __future__ import annotations
import aiohttp
import json
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
import os

from .base import OutageProvider, RegionMeta, DaySchedule, Slot

class TernopilProvider(OutageProvider):
    id = "ternopil"
    API_URL = "https://api-toe-poweron.inneti.net/api/actual_gpv_graphs"

    async def _fetch(self) -> dict:
        async with aiohttp.ClientSession() as s:
            async with s.get(self.API_URL) as r:
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
        
        try:
            data = await self._fetch()
            members = data.get("hydra:member", [])
        except Exception as e:
            print(f"Ternopil API fetch error: {e}")
            return None, None, 0

        # Determine target dates
        # Use simple date checking. 
        # Ideally we know "Today" from system time.
        # Let's use datetime.now() assuming server time is roughly correct for matching "2026-01-28" strings.
        # Since we just want to return "Today" and "Tomorrow" objects if they exist in the feed.
        
        # BUT the bot logic in app.py relies on "Today" being the actual today.
        # So we must identify which graph is today.
        
        # Note: user environment might be UTC, but dates in API are likely "local date" (00:00+00:00 offset in string but meaning local day).
        # Let's rely on string matching YYYY-MM-DD.
        
        # Actually, best practice: get today's date from system (with TZ if possible, or naive) and match.
        from datetime import timezone
        # Users TZ is +02:00 usually (Kyiv).
        # Let's just create today string.
        import pytz
        tz = pytz.timezone("Europe/Kyiv")
        now = datetime.now(tz)
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
            if target_key not in data_json:
                continue
                
            times = data_json[target_key]["times"]
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
