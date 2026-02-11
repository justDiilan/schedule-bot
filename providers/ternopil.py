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

    async def _fetch(self, params: dict, headers: dict = None) -> dict:
        print(f"DEBUG: Fetching {self.API_URL} with params: {params}")
        
        base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://poweron.toe.com.ua",
            "Referer": "https://poweron.toe.com.ua/",
        }
        if headers:
            base_headers.update(headers)

        async with aiohttp.ClientSession(headers=base_headers) as s:
            async with s.get(self.API_URL, params=params) as r:
                print(f"DEBUG: Response status: {r.status}")
                text = await r.text()
                print(f"DEBUG: Response body: {text[:1000]}...")
                r.raise_for_status()
                return json.loads(text)
    

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
        import base64
        from datetime import timezone
        
        # Dates setup:
        # API seems to use UTC (+00:00).
        # We need "Today" and "Tomorrow" relative to UA time.
        
        ua_tz = pytz.timezone("Europe/Kyiv")
        now_ua = datetime.now(ua_tz)
        
        # We want to cover Today and Tomorrow.
        # Let's request: Start of Yesterday UTC -> End of Tomorrow UTC.
        # Wider range is safer.
        
        # Get current time in UTC
        now_utc = datetime.now(timezone.utc)
        
        # Range: Now - 24h to Now + 48h
        t_after = now_utc - timedelta(days=1)
        t_before = now_utc + timedelta(days=2)
        
        # Format: YYYY-MM-DDTHH:MM:SS+00:00
        # Ensure we don't have microseconds
        t_after = t_after.replace(microsecond=0)
        t_before = t_before.replace(microsecond=0)
        
        # Calculate 'time' parameter based on known reference.
        # 2026-02-11 is 21299.
        # This seems to be days since approx Oct 1967.
        ref_date = datetime(2026, 2, 11, tzinfo=ua_tz).date()
        days_diff = (now_ua.date() - ref_date).days
        time_val = 21299 + days_diff
        
        debug_key = base64.b64encode(str(time_val).encode()).decode()
        
        params = {
            "after": t_after.isoformat(),
            "before": t_before.isoformat(),
            "group[]": f"{group}.{subgroup}",
            "time": time_val
        }
        
        req_headers = {
            "x-debug-key": debug_key
        }
        
        print(f"DEBUG: get_schedule params constructed: {params}")
        print(f"DEBUG: x-debug-key: {debug_key}")

        try:
            data = await self._fetch(params, headers=req_headers)
            members = data.get("hydra:member", [])
            print(f"DEBUG: Found {len(members)} graph members")
        except Exception as e:
            print(f"Ternopil API fetch error: {e}")
            return None, None, 0

        today_str = now_ua.strftime("%Y-%m-%d")
        tomorrow_str = (now_ua + timedelta(days=1)).strftime("%Y-%m-%d")

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
