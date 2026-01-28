from __future__ import annotations
import hashlib
from typing import Optional
from providers.base import DaySchedule

def schedule_to_text(region_name: str, day: Optional[DaySchedule], header: str = None) -> str:
    if not day:
        return f"🗺️ {region_name}\n\n⚠️ Немає даних по розкладу."

    if header:
        title_line = f"🔔 <b>{header}</b>\n🗺️ {region_name}"
    else:
        title_line = f"🗺️ <b>{region_name}</b>"

    lines = [
        title_line,
        f"👥 <b>Група:</b> {day.group_key}",
        f"🗓️ <b>Дані:</b> {day.title}",
        "",
    ]
    if not day.outages:
        lines.append("✅ Сьогодні відключень не заплановано (за даними джерела).")
    else:
        lines.append("⛔ <b>Відключення:</b>")
        
        # Intelligent merging logic
        # We want to merge "outage" + "switching" into one line
        i = 0
        slots = day.outages
        while i < len(slots):
            current = slots[i]
            
            # Look ahead for mergeable slot
            next_slot = slots[i+1] if i + 1 < len(slots) else None
            
            # Case 1: Outage then Switching (Power ON process)
            if next_slot and current.kind == "outage" and next_slot.kind == "switching" and current.end == next_slot.start:
                lines.append(f" • {current.start} — {next_slot.end} 🟡 (увімкнення з {current.end})")
                i += 2 # Skip both
                continue
                
            # Case 2: Switching then Outage (Power OFF process)
            if next_slot and current.kind == "switching" and next_slot.kind == "outage" and current.end == next_slot.start:
                lines.append(f" • {current.start} — {next_slot.end} 🟡 (вимкнення з {current.start})")
                i += 2 # Skip both
                continue
            
            # Default case
            icon = "🟡" if current.kind == "switching" else "•"
            note = " (можливе відключення/перемикання)" if current.kind == "switching" else ""
            lines.append(f" {icon} {current.start} — {current.end}{note}")
            i += 1
            
    return "\n".join(lines)

def get_day_hash(day: Optional[DaySchedule]) -> str:
    if not day:
        return ""
    # Мы хешируем только outages, так как title и group_key могут не меняться
    # А вот если поменялись слоты — это важно.
    base = str(day.outages)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()
