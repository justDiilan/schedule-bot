from __future__ import annotations

import aiohttp
import json
import time
from typing import List, Optional, Tuple, Dict

from .base import OutageProvider, RegionMeta, DaySchedule, Slot

OLD_API_URL = "https://svitlo-proxy.svitlo-proxy.workers.dev"

class SvitloProvider(OutageProvider):
    id = "svitlo"

    async def _fetch(self, url: str) -> dict:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=25)) as r:
                r.raise_for_status()
                data = await r.json()
                if isinstance(data, dict) and "body" in data:
                    return json.loads(data["body"])
                return data

    async def _fetch_any(self) -> dict:
        return await self._fetch(OLD_API_URL)

    # ---------- helpers ----------
    def _extract_groups(self, region_obj: dict) -> Dict[str, dict]:
        # основной формат svitlo.live
        return region_obj.get("schedule") or {}

    def _slots_to_intervals(self, slots: dict) -> list[Slot]:
        """
        2 = outage
        1 = power
        0 = no data

        Интервал считается:
          старт = момент перехода X -> 2
          конец  = момент перехода 2 -> X
        """

        def to_minutes(t: str) -> int:
            h, m = t.split(":")
            return int(h) * 60 + int(m)

        times = sorted(slots.keys(), key=to_minutes)

        outages = []

        prev_val = None
        prev_time = None

        for t in times:
            val = slots[t]

            # Переход В отключение
            if val == 2 and prev_val != 2:
                start_time = t

            # Переход ИЗ отключения
            if prev_val == 2 and val != 2:
                outages.append(Slot(
                    start=start_time,
                    end=t,
                    kind="outage"
                ))

            prev_val = val
            prev_time = t

        # Если день закончился в отключении
        if prev_val == 2:
            outages.append(Slot(
                start=start_time,
                end="24:00",
                kind="outage"
            ))

        print("DEBUG OUTAGES:", outages)
        return outages

    # ---------- API ----------
    async def list_regions(self) -> List[RegionMeta]:
        data = await self._fetch_any()
        regions = data.get("regions", [])

        metas: List[RegionMeta] = []

        for r in regions:
            code = str(r.get("cpu") or "").strip()
            name = (
                str(r.get("name_ua"))
                or str(r.get("name"))
                or code
            )

            sched = self._extract_groups(r)

            group_nums = set()
            sub_nums = set()

            for key in sched.keys():
                if "." in key:
                    g, sg = key.split(".", 1)
                    if g.isdigit():
                        group_nums.add(g)
                    if sg.isdigit():
                        sub_nums.add(sg)

            if not group_nums:
                group_nums = {"1", "2", "3", "4", "5", "6"}
            if not sub_nums:
                sub_nums = {"1", "2"}

            metas.append(RegionMeta(
                code=code,
                name=name,
                groups=sorted(group_nums, key=int),
                subgroups=sorted(sub_nums, key=int),
            ))

        return metas

    async def get_schedule(
        self,
        region_code: str,
        group: str,
        subgroup: str
    ) -> Tuple[Optional[DaySchedule], Optional[DaySchedule], int]:

        data = await self._fetch_any()
        regions = data.get("regions", [])

        region = next(
            (r for r in regions if str(r.get("cpu")).lower() == region_code.lower()),
            None
        )

        if not region:
            return None, None, 0

        sched = self._extract_groups(region)
        key = f"{group}.{subgroup}"

        group_block = sched.get(key)
        if not group_block:
            return None, None, 0

        today_date = data.get("date_today")
        tomorrow_date = data.get("date_tomorrow")

        def build_day(date_str: str, title: str) -> Optional[DaySchedule]:
            day_slots = group_block.get(date_str)
            if not day_slots:
                return None

            # Фильтруем "пустые" дни, где все значения 0 (нет данных)
            # Если там есть хоть одна 1 (свет) или 2 (отключение) — тогда это график.
            if all(v == 0 for v in day_slots.values()):
                return None

            outages = self._slots_to_intervals(day_slots)

            return DaySchedule(
                title=title,
                date=date_str,
                group_key=key,
                outages=outages
            )

        today = build_day(today_date, f"Сьогодні: {today_date}")
        tomorrow = build_day(tomorrow_date, f"Завтра: {tomorrow_date}")

        return today, tomorrow, 0
