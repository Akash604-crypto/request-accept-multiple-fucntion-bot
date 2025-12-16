"""
Telegram Auto Request Accept Bot
Author: botmaker Spec

SECURED VERSION
- Only ADMIN / allowed users can control bot
"""

import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ChatJoinRequestHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -------------------- ENV --------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID"))

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
CHANNELS_FILE = DATA_DIR / "channels.json"
STATS_FILE = DATA_DIR / "stats.json"
ALLOWED_USERS_FILE = DATA_DIR / "allowed_users.json"

# -------------------- LOAD / SAVE --------------------
def load_json(file: Path, default):
    if file.exists():
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(file: Path, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

users: Dict[str, dict] = load_json(USERS_FILE, {})
channels = load_json(CHANNELS_FILE, [])
stats = load_json(STATS_FILE, {
    "approved_requests": 0,
    "broadcasts": 0,
    "blocked_users": 0
})
allowed_users = set(load_json(ALLOWED_USERS_FILE, []))

def save_all():
    save_json(USERS_FILE, users)
    save_json(CHANNELS_FILE, channels)
    save_json(STATS_FILE, stats)

def save_allowed_users():
    save_json(ALLOWED_USERS_FILE, list(allowed_users))

# -------------------- SECURITY --------------------
def is_admin(update: Update) -> bool:
    if not update.effective_user:
        return False
    uid = update.effective_user.id
    return uid == ADMIN_CHAT_ID or uid in allowed_users

async def deny(update: Update):
    await update.message.reply_text("❌ You are not authorized to use this bot.")

# -------------------- AUTO APPROVE --------------------
async def auto_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    chat_id = req.chat.id

    if chat_id not in channels:
        return

    try:
        await req.approve()
        stats["approved_requests"] += 1

        user = req.from_user
        users[str(user.id)] = {
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "channel_id": chat_id,
            "joined_at": datetime.utcnow().isoformat(),
        }

        save_all()

        await context.bot.send_message(
            chat_id=user.id,
            text="✅ Your request has been approved!\n\nWelcome 🎉",
        )

    except Exception as e:
        print("Auto-approve error:", e)

# -------------------- START --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text(
            "🚫 Access Restricted\n\n"
            "Contact here for access 👉 @Vip_Help_center1222_bot"
        )
        return

    await update.message.reply_text(
        "👋 Welcome\n\n"
        "Available Commands:\n"
        "/addchannel <channel_id>\n"
        "/broadcast\n"
        "/broadcastforwardmsg\n"
        "/stats\n"
        "/giveaccess <user_id>"
    )

# -------------------- ADMIN COMMANDS --------------------
async def run_broadcast(message, mode, users, context):
    user_ids = list(users.keys())  # 🔒 freeze list
    total = len(user_ids)
    sent = 0
    blocked = 0
    last_percent = -1

    progress_msg = await context.bot.send_message(
        chat_id=message.chat_id,
        text="📢 Broadcast started...\n📊 0%"
    )

    for index, uid in enumerate(user_ids, start=1):
        try:
            if mode == "copy":
                await message.copy(chat_id=int(uid))
            else:
                await message.forward(chat_id=int(uid))

            sent += 1
            await asyncio.sleep(0.05)

        except Exception as e:
            if "blocked by the user" in str(e).lower():
                blocked += 1
                users.pop(uid, None)

        percent = int((index / total) * 100)

        # 🔁 Update only when % actually changes
        if percent % 5 == 0 and percent != last_percent:
            last_percent = percent
            try:
                await progress_msg.edit_text(
                    f"📢 Broadcast in progress...\n"
                    f"📊 {index} / {total} sent ({percent}%)"
                )
            except:
                pass

    stats["broadcasts"] += 1
    stats["blocked_users"] += blocked
    save_all()

    try:
        await progress_msg.edit_text(
            f"✅ Broadcast Completed\n\n"
            f"📤 Sent: {sent}\n"
            f"🚫 Blocked: {blocked}\n"
            f"📊 Total: {total}"
        )
    except:
        pass


async def give_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Only main admin can grant access.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /giveaccess <user_id>")
        return

    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID.")
        return

    allowed_users.add(uid)
    save_allowed_users()

    await update.message.reply_text(f"✅ Access granted to user `{uid}`", parse_mode="Markdown")

    try:
        await context.bot.send_message(
            chat_id=uid,
            text="✅ You have been granted access to the bot."
        )
    except:
        pass

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await deny(update)
        return

    if not context.args:
        await update.message.reply_text("Usage: /addchannel <channel_id>")
        return

    try:
        cid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid channel ID.")
        return

    if cid not in channels:
        channels.append(cid)
        save_all()
        await update.message.reply_text("✅ Channel added successfully.")
    else:
        await update.message.reply_text("ℹ️ Channel already exists.")

# -------------------- BROADCAST --------------------
BROADCAST_MODE = {}

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await deny(update)
        return

    chat_id = update.effective_chat.id

    # ✅ ADD THIS GUARD
    if chat_id in BROADCAST_MODE:
        await update.message.reply_text("⚠️ Broadcast already pending.")
        return

    BROADCAST_MODE[chat_id] = "copy"
    await update.message.reply_text("📢 Send message to broadcast (DM only).")


async def broadcast_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await deny(update)
        return

    chat_id = update.effective_chat.id

    # ✅ ADD THIS GUARD
    if chat_id in BROADCAST_MODE:
        await update.message.reply_text("⚠️ Broadcast already pending.")
        return

    BROADCAST_MODE[chat_id] = "forward"
    await update.message.reply_text("📨 Forward message to broadcast.")

async def clear_broadcast_later(chat_id, delay=300):
    await asyncio.sleep(delay)
    BROADCAST_MODE.pop(chat_id, None)



async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id

    if chat_id not in BROADCAST_MODE:
        return

    if not is_admin(update):
        return

    mode = BROADCAST_MODE.pop(chat_id)

    # 🔥 Run broadcast in background (NON-BLOCKING)
    asyncio.create_task(
        run_broadcast(update.message, mode, users, context)
    )


# -------------------- STATS --------------------
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await deny(update)
        return

    total_users = len(users)
    blocked_users = stats.get("blocked_users", 0)

    await update.message.reply_text(
        f"📊 Bot Stats\n\n"
        f"👥 Active Users: {total_users}\n"
        f"📢 Channels: {len(channels)}\n"
        f"✅ Approved Requests: {stats['approved_requests']}\n"
        f"📨 Broadcasts: {stats['broadcasts']}\n"
        f"🚫 Total Blocked (lifetime): {blocked_users}"
    )


# -------------------- MAIN --------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("giveaccess", give_access))
    app.add_handler(CommandHandler("addchannel", add_channel))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("broadcastforwardmsg", broadcast_forward))
    app.add_handler(CommandHandler("stats", stats_cmd))

    app.add_handler(ChatJoinRequestHandler(auto_approve))
    app.add_handler(
        MessageHandler(
            filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL,

            handle_broadcast
        )
    )



    print("🤖 Secure admin bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
