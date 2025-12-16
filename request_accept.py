"""
Telegram Auto Request Accept Bot
Author: botmaker Spec

SECURED VERSION
- Only ADMIN / allowed users can control bot
"""

import os
import json
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

    BROADCAST_MODE[update.effective_chat.id] = "copy"
    await update.message.reply_text("📢 Send message to broadcast (DM only).")

async def broadcast_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await deny(update)
        return

    BROADCAST_MODE[update.effective_chat.id] = "forward"
    await update.message.reply_text("📨 Forward message to broadcast.")

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id

    if chat_id not in BROADCAST_MODE:
        return

    if not is_admin(update):
        return

    mode = BROADCAST_MODE.pop(chat_id)
    sent = 0

    for uid in list(users.keys()):
        try:
            if mode == "copy":
                await update.message.copy(chat_id=int(uid))
            else:
                await update.message.forward(chat_id=int(uid))
            sent += 1
        except:
            pass

    stats["broadcasts"] += 1
    save_all()

    await update.message.reply_text(f"✅ Broadcast sent to {sent} users.")


# -------------------- STATS --------------------
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await deny(update)
        return

    await update.message.reply_text(
        f"📊 Bot Stats\n\n"
        f"👥 Users: {len(users)}\n"
        f"📢 Channels: {len(channels)}\n"
        f"✅ Approved Requests: {stats['approved_requests']}\n"
        f"📨 Broadcasts: {stats['broadcasts']}"
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
            filters.TEXT | filters.PHOTO | filters.VIDEO | filters.DOCUMENT,
            handle_broadcast
        )
    )



    print("🤖 Secure admin bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
