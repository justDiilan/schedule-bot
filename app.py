from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

class FeedbackState(StatesGroup):
    waiting_for_message = State()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from db import DB
from providers import build_providers
from formatting import schedule_to_text, get_day_hash


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "180"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Kyiv")
ADMIN_ID = 857110651

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty. Put it into .env")

bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()
db_path = os.getenv("DB_PATH", "bot.db")
db = DB(db_path)
providers = build_providers()

# --- UI helpers ---
# --- UI helpers ---
async def kb_all_regions():
    kb = InlineKeyboardBuilder()
    
    for prov_id, prov in providers.items():
        try:
            regions = await prov.list_regions()
            for r in regions:
                # Filter duplicates: If Svitlo provider returns Ternopil, ignore it
                # because we have a dedicated "ternopil" provider now.
                if prov_id == "svitlo" and ("тернопіль" in r.name.lower() or "ternopil" in r.code.lower()):
                    continue

                kb.button(text=r.name, callback_data=f"reg:{prov_id}:{r.code}")
        except Exception as e:
            print(f"Error fetching regions from {prov_id}: {e}")
            
    kb.adjust(2)
    return kb.as_markup()

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
        [InlineKeyboardButton(text="⚙️ Змінити регіон", callback_data="act:start")],
        [InlineKeyboardButton(text="✍️ Написати розробнику", callback_data="act:feedback_info")]
    ])

# --- handlers ---
# --- imports fixed ---
from formatting import schedule_to_text, get_day_hash

# ... (imports remain) ...

# --- UI helpers (remain same) ---

# --- handlers ---
@dp.message(CommandStart())
async def start(m: Message):
    # Try to capture/update username even if not subscribing yet.
    existing = db.get_subscription(m.from_user.id)
    if existing:
         username = m.from_user.username or m.from_user.first_name
         db.upsert_subscription(existing.user_id, existing.provider, existing.region_code, existing.group_num, existing.subgroup_num, username=username)

    # Show all regions from ALL providers
    kb = await kb_all_regions()
    await m.answer("Привіт! Обери свій регіон:", reply_markup=kb)

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

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    # Update admin's username if missing/changed
    existing = db.get_subscription(message.from_user.id)
    if existing:
         username = message.from_user.username or message.from_user.first_name
         db.upsert_subscription(existing.user_id, existing.provider, existing.region_code, existing.group_num, existing.subgroup_num, username=username)
    
    stats = db.get_stats()
    count = len(stats)
    
    # Show last 20 users
    last_users = stats[-20:]
    text_lines = [f"📊 <b>Statistics</b>", f"Total Users: {count}", ""]
    text_lines.append("<b>Last 20 Users:</b>")
    for uid, uname in last_users:
        if uname:
             # Basic escape for HTML just in case
             safe_uname = uname.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
             u_str = f"@{safe_uname}"
        else:
             u_str = "No username"
        
        text_lines.append(f"<code>{uid}</code> - {u_str}")
        
    await message.answer("\n".join(text_lines), parse_mode="HTML")

@dp.message(Command("feedback"))
async def cmd_feedback(message: Message):
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        await message.answer("📝 Щоб надіслати повідомлення розробнику, напиши:\n<code>/feedback Текст повідомлення</code>", parse_mode="HTML")
        return
        
    feedback_text = parts[1]
    user = message.from_user
    
    # Format info about sender
    # Use HTML escape for safety
    safe_name = (user.full_name or "Unknown").replace("<", "&lt;").replace(">", "&gt;")
    safe_uname = f"@{user.username}" if user.username else "No username"
    
    admin_text = (
        f"📨 <b>NEW FEEDBACK</b>\n"
        f"From: {safe_name} ({safe_uname})\n"
        f"ID: <code>{user.id}</code>\n\n"
        f"{feedback_text.replace('<', '&lt;').replace('>', '&gt;')}"
    )
    
    try:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
        await message.answer("✅ Ваше повідомлення надіслано розробнику! Дякую.")
    except Exception as e:
        print(f"Failed to send feedback from {user.id}: {e}")
        await message.answer("❌ Помилка при надсиланні. Спробуйте пізніше.")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
        
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        await message.answer("Usage: /broadcast <text>")
        return
        
    text = parts[1]
    user_ids = db.get_all_user_ids()
    
    sent = 0
    blocked = 0
    failed = 0
    
    status_msg = await message.answer(f"🚀 Starting broadcast to {len(user_ids)} users...")
    
    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
            sent += 1
        except TelegramForbiddenError:
            db.delete_subscription(uid)
            blocked += 1
        except Exception as e:
            print(f"Failed to send to {uid}: {e}")
            failed += 1
        # Small delay to avoid hitting limits too hard
        await asyncio.sleep(0.05)
            
    await status_msg.edit_text(
        f"✅ **Broadcast Complete**\n"
        f"Sent: {sent}\n"
        f"Blocked (removed): {blocked}\n"
        f"Failed: {failed}"
    )

@dp.callback_query(F.data.startswith("sub:"))
async def pick_subgroup(cb: CallbackQuery):
    _, prov_id, region_code, group_num, subgroup_num = cb.data.split(":")
    
    username = cb.from_user.username or cb.from_user.first_name
    db.upsert_subscription(cb.from_user.id, prov_id, region_code, group_num, subgroup_num, username=username)

    await cb.message.edit_text("✅ Збережено! Отримую актуальний графік…")
    await cb.answer()

    await process_subscription(cb.from_user.id, mode="first_run")

@dp.callback_query(F.data == "act:refresh")
async def act_refresh(cb: CallbackQuery):
    await cb.answer("Оновлюю...")
    await process_subscription(cb.from_user.id, mode="refresh")

@dp.callback_query(F.data == "act:start")
async def act_start(cb: CallbackQuery):
    await start(cb.message)

@dp.callback_query(F.data == "act:feedback_info")
async def act_feedback_info(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(FeedbackState.waiting_for_message)
    await cb.message.answer("✍️ <b>Напишіть ваше повідомлення прямо зараз:</b>\n\n(Можете описати проблему або пропозицію, я передам розробнику)", parse_mode="HTML")

@dp.message(FeedbackState.waiting_for_message)
async def feedback_message_handler(message: Message, state: FSMContext):
    # Capture message logic similar to cmd_feedback but without command parsing
    user = message.from_user
    feedback_text = message.text or "[Not text message]"

    safe_name = (user.full_name or "Unknown").replace("<", "&lt;").replace(">", "&gt;")
    safe_uname = f"@{user.username}" if user.username else "No username"

    admin_text = (
        f"📨 <b>NEW FEEDBACK (via Button)</b>\n"
        f"From: {safe_name} ({safe_uname})\n"
        f"ID: <code>{user.id}</code>\n\n"
        f"{feedback_text.replace('<', '&lt;').replace('>', '&gt;')}"
    )

    try:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
        await message.answer("✅ <b>Відправлено!</b> Дякую за зворотній зв'язок.", parse_mode="HTML")
    except Exception as e:
        print(f"Failed to send feedback from {user.id}: {e}")
        await message.answer("❌ Помилка при надсиланні. Спробуйте пізніше.")
    
    await state.clear()


# --- Core Logic ---

async def send_schedule_message(user_id: int, region_name: str, day, is_tomorrow: bool, header: str = None):
    title = region_name + " (ЗАВТРА)" if is_tomorrow else region_name
    text = schedule_to_text(title, day, header=header)
    await bot.send_message(user_id, text, reply_markup=kb_actions())

async def process_subscription(user_id: int, mode: str = "poll"):
    """
    mode: 
      "poll"      - automatic check (compares hashes)
      "refresh"   - user clicked refresh (force today)
      "first_run" - user just subscribed (force today)
    """
    sub = db.get_subscription(user_id)
    if not sub:
        if mode != "poll":
            await bot.send_message(user_id, "Немає підписки. Натисни /start")
        return

    prov = providers.get(sub.provider)
    if not prov:
        return

    # 1. Fetch data
    try:
        today, tomorrow, _ = await prov.get_schedule(sub.region_code, sub.group_num, sub.subgroup_num)
    except Exception as e:
        print(f"Error fetching schedule for {user_id}: {e}")
        return

    # 2. Helpers for state management
    def parse_state(state_str):
        # Format: "date|hash" or just "hash" (legacy)
        if "|" in state_str:
            return state_str.split("|", 1)
        return "", state_str

    def make_state(day_obj, day_hash):
        if not day_obj:
            return "" # Empty state
        # day_obj.date comes from our updated DaySchedule
        return f"{day_obj.date}|{day_hash}"

    # 3. Calculate current state
    h_today = get_day_hash(today)
    h_tomorrow = get_day_hash(tomorrow)
    
    current_today_state = make_state(today, h_today)
    current_tomorrow_state = make_state(tomorrow, h_tomorrow)
    new_combined_hash = f"{current_today_state}:{current_tomorrow_state}"

    # 4. Get stored state
    stored = sub.last_hash
    if ":" in stored:
        stored_today_full, stored_tomorrow_full = stored.split(":", 1)
    else:
        stored_today_full, stored_tomorrow_full = stored, ""
        
    s_today_date, s_today_hash = parse_state(stored_today_full)
    s_tomorrow_date, s_tomorrow_hash = parse_state(stored_tomorrow_full)

    # 5. Resolve Region Name
    regions = await prov.list_regions()
    region_name = next((r.name for r in regions if r.code == sub.region_code), sub.region_code)

    # 6. Logic based on mode
    if mode == "poll":
        # --- Check Today ---
        today_changed = False
        if not today:
            pass # No data for today, strange but skip
        else:
            # If dates differ, it's a rollover (or new subscription)
            if today.date != s_today_date:
                # Rollover logic:
                # We interpret this as a change ONLY if it differs from what we knew as "tomorrow".
                
                # Check 1: We expected this (it matches yesterday's tomorrow) -> SILENT
                if s_tomorrow_hash and (h_today == s_tomorrow_hash):
                    pass # Verified match, silent rollover.

                # Check 2: We didn't expect this, or it changed -> ALERT
                else:
                     # Either s_tomorrow_hash was empty (late publication), 
                     # OR it existed but h_today is different (update).
                     header = "УВАГА! Графік змінився (оновлення)!" if s_tomorrow_hash else "З'явився графік на сьогодні!"
                     await send_schedule_message(user_id, region_name, today, is_tomorrow=False, header=header)
                     today_changed = True
            
            # If dates are same, check hash
            elif h_today != s_today_hash:
                await send_schedule_message(user_id, region_name, today, is_tomorrow=False, header="УВАГА! Графік змінився!")
                today_changed = True
        
        # --- Check Tomorrow ---
        tomorrow_changed = False
        if tomorrow:
            # If date different (new day appearing) -> ALERT
            if tomorrow.date != s_tomorrow_date:
                await send_schedule_message(user_id, region_name, tomorrow, is_tomorrow=True, header="З'явився/змінився графік на завтра!")
                tomorrow_changed = True
            # If date same but hash diff -> ALERT
            elif h_tomorrow != s_tomorrow_hash:
                 await send_schedule_message(user_id, region_name, tomorrow, is_tomorrow=True, header="УВАГА! Графік на завтра змінився!")
                 tomorrow_changed = True

        # Save state if anything "changed" in our state representation
        # We always update DB if there's any diff in string representation to stay in sync
        if new_combined_hash != stored:
             db.set_last_hash(user_id, new_combined_hash)

    elif mode in ("refresh", "first_run"):
        # Always send Today
        await send_schedule_message(user_id, region_name, today, is_tomorrow=False)
        
        # If tomorrow exists, send it too! (Otherwise we update DB hash and "swallow" the notification)
        if tomorrow:
             await send_schedule_message(user_id, region_name, tomorrow, is_tomorrow=True)
        # Update DB 
        db.set_last_hash(user_id, new_combined_hash)


async def poll_updates_job():
    subs = db.list_subscriptions()
    for s in subs:
        try:
            await process_subscription(s.user_id, mode="poll")
        except TelegramForbiddenError:
            print(f"User {s.user_id} blocked the bot. Removing.")
            db.delete_subscription(s.user_id)
        except Exception as e:
            print(f"Error in poll_updates_job for {s.user_id}: {e}")

# We don't need daily_tomorrow_job anymore because poll_updates_job 
# will detect when 'tomorrow' appears/changes and send it immediately.

async def main():
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    scheduler.add_job(poll_updates_job, "interval", seconds=POLL_SECONDS)

    scheduler.start()
    print("SCHEDULER STARTED")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
