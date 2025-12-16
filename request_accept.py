"""
Telegram Auto Request Accept Bot
Author: botmaker Spec
Features:
- Auto approve join requests (channels & groups)
- Persistent storage (Render-safe)
- Admin broadcast to users only
- Admin utilities
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

# -------------------- HELPERS --------------------
def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_CHAT_ID


def save_all():
    save_json(USERS_FILE, users)
    save_json(CHANNELS_FILE, channels)
    save_json(STATS_FILE, stats)


# -------------------- JOIN REQUEST AUTO-APPROVE --------------------
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
            "joined_at": datetime.utcnow().isoformat(),
            "channel_id": chat_id,
        }

        save_all()

        # Welcome message (DM)
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "✅ Your request has been approved!\n\n"
                "Welcome 🎉\n"
                "Enjoy the content and stay active."
            )
        )

    except Exception as e:
        print("Auto approve error:", e)


# -------------------- ADMIN COMMANDS --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Auto Request Accept Bot is running.\n"
        "Admin commands available."
    )


async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /addchannel <channel_id>")
        return

    cid = int(context.args[0])
    if cid not in channels:
        channels.append(cid)
        save_all()
        await update.message.reply_text("✅ Channel added. Auto-accept enabled.")
    else:
        await update.message.reply_text("ℹ️ Channel already exists.")


async def approve_old(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /approveoldreq <channel_id>")
        return

    cid = int(context.args[0])
    count = 0

    try:
        async for req in context.bot.get_chat_join_requests(cid):
            await req.approve()
            count += 1

        await update.message.reply_text(f"✅ Approved {count} old requests.")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def del_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /delall <chat_id>")
        return

    chat_id = int(context.args[0])

    try:
        async for msg in context.bot.get_chat_history(chat_id):
            await context.bot.delete_message(chat_id, msg.message_id)

        await update.message.reply_text("🧹 All messages deleted.")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# -------------------- BROADCAST (USERS ONLY) --------------------
BROADCAST_MODE = {}

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    BROADCAST_MODE[update.effective_chat.id] = "copy"
    await update.message.reply_text(
        "📢 Send the message now.\n"
        "It will be sent to ALL users (DM only)."
    )


async def broadcast_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    BROADCAST_MODE[update.effective_chat.id] = "forward"
    await update.message.reply_text(
        "📨 Forward a message now.\n"
        "Sender name will remain visible."
    )


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in BROADCAST_MODE:
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


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
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
    app.add_handler(CommandHandler("addchannel", add_channel))
    app.add_handler(CommandHandler("approveoldreq", approve_old))
    app.add_handler(CommandHandler("delall", del_all))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("broadcastforwardmsg", broadcast_forward))
    app.add_handler(CommandHandler("stats", stats_cmd))

    app.add_handler(ChatJoinRequestHandler(auto_approve))
    app.add_handler(MessageHandler(filters.ALL, handle_broadcast))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
