from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from db import DB
from providers import build_providers
from formatting import schedule_to_text, schedule_hash

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "180"))
DAILY_SEND_HOUR = int(os.getenv("DAILY_SEND_HOUR", "20"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Kyiv")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty. Put it into .env")

bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()
db_path = os.getenv("DB_PATH", "bot.db")
db = DB(db_path)
providers = build_providers()

# --- UI helpers ---
async def kb_regions(provider_id: str):
    prov = providers[provider_id]
    regions = await prov.list_regions()
    kb = InlineKeyboardBuilder()
    for r in regions:
        kb.button(text=r.name, callback_data=f"reg:{provider_id}:{r.code}")
    kb.adjust(2)
    return kb.as_markup(), {r.code: r.name for r in regions}

async def kb_groups(provider_id: str, region_code: str):
    prov = providers[provider_id]
    regions = await prov.list_regions()
    meta = next((x for x in regions if x.code == region_code), None)
    if not meta:
        return None, None

    kb = InlineKeyboardBuilder()
    for g in meta.groups:
        kb.button(text=f"Група {g}", callback_data=f"grp:{provider_id}:{region_code}:{g}")
    kb.adjust(3)
    return kb.as_markup(), meta

def kb_subgroups(provider_id: str, region_code: str, group_num: str, subgroups: list[str]):
    kb = InlineKeyboardBuilder()
    for sg in subgroups:
        kb.button(text=f"Підгрупа {sg}", callback_data=f"sub:{provider_id}:{region_code}:{group_num}:{sg}")
    kb.adjust(2)
    return kb.as_markup()

def kb_actions():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Оновити", callback_data="act:refresh")],
        [InlineKeyboardButton(text="⚙️ Змінити регіон", callback_data="act:start")]
    ])

# --- handlers ---
@dp.message(CommandStart())
async def start(m: Message):
    # Default to "svitlo" provider
    prov_id = "svitlo"
    kb, _ = await kb_regions(prov_id)
    await m.answer("Привіт! Обери регіон (Svitlo Live):", reply_markup=kb)

@dp.callback_query(F.data.startswith("reg:"))
async def pick_region(cb: CallbackQuery):
    _, prov_id, region_code = cb.data.split(":")
    kb, meta = await kb_groups(prov_id, region_code)
    if not kb:
        await cb.message.edit_text("Не знайшов регіон. Спробуй /start ще раз.")
        await cb.answer()
        return
    await cb.message.edit_text(f"Обери групу для <b>{meta.name}</b>:", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("grp:"))
async def pick_group(cb: CallbackQuery):
    _, prov_id, region_code, group_num = cb.data.split(":")
    prov = providers[prov_id]
    regions = await prov.list_regions()
    meta = next((x for x in regions if x.code == region_code), None)
    if not meta:
        await cb.message.edit_text("Не знайшов дані регіону. /start")
        await cb.answer()
        return

    kb = kb_subgroups(prov_id, region_code, group_num, meta.subgroups)
    await cb.message.edit_text(f"Група <b>{group_num}</b>. Тепер обери підгрупу:", reply_markup=kb)
    await cb.answer()

@dp.callback_query(F.data.startswith("sub:"))
async def pick_subgroup(cb: CallbackQuery):
    _, prov_id, region_code, group_num, subgroup_num = cb.data.split(":")
    db.upsert_subscription(cb.from_user.id, prov_id, region_code, group_num, subgroup_num)

    await cb.message.edit_text("✅ Збережено! Отримую актуальний графік…")
    await cb.answer()

    await send_current_schedule(cb.from_user.id, force=True)

@dp.callback_query(F.data == "act:refresh")
async def act_refresh(cb: CallbackQuery):
    await cb.answer("Оновлюю...")
    await send_current_schedule(cb.from_user.id, force=True)

@dp.callback_query(F.data == "act:start")
async def act_start(cb: CallbackQuery):
    await start(cb.message)


# --- sending logic ---
async def send_current_schedule(user_id: int, force: bool = False, send_tomorrow: bool = False):
    sub = db.get_subscription(user_id)
    if not sub:
        await bot.send_message(user_id, "Немає підписки. Натисни /start")
        return

    prov = providers.get(sub.provider)
    if not prov:
        await bot.send_message(user_id, "Провайдер недоступний. Натисни /start")
        return

    regions = await prov.list_regions()
    region_name = next((r.name for r in regions if r.code == sub.region_code), sub.region_code)

    today, tomorrow, last_update = await prov.get_schedule(sub.region_code, sub.group_num, sub.subgroup_num)
    h = schedule_hash(today, tomorrow, last_update)

    if (not force) and (h == sub.last_hash):
        return

    if send_tomorrow:
        text = schedule_to_text(region_name + " (ЗАВТРА)", tomorrow)
    else:
        text = schedule_to_text(region_name, today)

    await bot.send_message(user_id, text, reply_markup=kb_actions())
    db.set_last_hash(user_id, h)

async def poll_updates_job():
    subs = db.list_subscriptions()
    for s in subs:
        try:
            await send_current_schedule(s.user_id, force=False)
        except Exception as e:
            # лучше логировать в файл, но не будем ломать рассылку всем
            print("ERROR:", e)

async def daily_tomorrow_job():
    subs = db.list_subscriptions()
    for s in subs:
        try:
            await send_current_schedule(s.user_id, force=True, send_tomorrow=True)
        except Exception:
            pass

async def main():
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # просто передаём корутины — БЕЗ lambda и create_task
    scheduler.add_job(poll_updates_job, "interval", seconds=POLL_SECONDS)
    scheduler.add_job(daily_tomorrow_job, "cron", hour=DAILY_SEND_HOUR, minute=0)

    scheduler.start()
    print("SCHEDULER STARTED")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
