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
        for s in day.outages:
            # если хочешь, можно красиво маппить kind -> текст
            lines.append(f" • {s.start} — {s.end}")
    return "\n".join(lines)

def get_day_hash(day: Optional[DaySchedule]) -> str:
    if not day:
        return ""
    # Мы хешируем только outages, так как title и group_key могут не меняться
    # А вот если поменялись слоты — это важно.
    base = str(day.outages)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()
