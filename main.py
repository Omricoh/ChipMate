import os
import logging
from datetime import datetime
from pymongo import MongoClient
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# --------- Config ---------
TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")

# Setup logging
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("chipbot")

# DB
client = MongoClient(MONGO_URL)
db = client["chipbot"]

# --------- Commands ---------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Command /start from user %s", update.effective_user.id)
    await update.message.reply_text("🎲 ChipBot ready! Use /newgame to start a game.")

async def newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    host = update.effective_user
    game = {
        "host_id": host.id,
        "host_name": host.first_name,
        "status": "active",
        "created_at": datetime.utcnow(),
    }
    res = db.games.insert_one(game)
    gid = str(res.inserted_id)
    logger.info("New game %s created by host %s", gid, host.id)
    await update.message.reply_text(
        f"New game started by {host.first_name}! 🎮\n"
        f"Game ID: {gid}\n"
        f"Players can join with /join {gid}"
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /join <game_id>")
        return
    gid = context.args[0]
    user = update.effective_user
    player = {
        "game_id": gid,
        "user_id": user.id,
        "name": user.first_name,
        "buyins": [],
        "final_chips": None,
        "quit": False,
    }
    db.players.update_one(
        {"game_id": gid, "user_id": user.id}, {"$set": player}, upsert=True
    )
    logger.info("Player %s joined game %s", user.id, gid)
    await update.message.reply_text(f"{user.first_name} joined game {gid} ✅")

async def buyin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /buyin <cash/register> <amount> <game_id>")
        return
    buy_type, amount = context.args[0], int(context.args[1])
    gid = context.args[2] if len(context.args) > 2 else None
    user = update.effective_user
    if not gid:
        await update.message.reply_text("Need a game ID")
        return
    tx = {
        "game_id": gid,
        "user_id": user.id,
        "type": f"buyin_{buy_type}",
        "amount": amount,
        "confirmed": False,
        "at": datetime.utcnow(),
    }
    db.transactions.insert_one(tx)
    logger.info("Player %s requested %s buyin of %s chips in game %s",
                user.id, buy_type, amount, gid)
    await update.message.reply_text(
        f"Buy-in request: {buy_type} {amount} chips (waiting host confirm)."
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /status <game_id>")
        return
    gid = context.args[0]
    user = update.effective_user
    player = db.players.find_one({"game_id": gid, "user_id": user.id})
    if not player:
        await update.message.reply_text("You are not in this game.")
        return
    logger.info("Status requested by user %s in game %s", user.id, gid)
    await update.message.reply_text(
        f"Game {gid} — Buyins: {player.get('buyins', [])}, "
        f"Final Chips: {player.get('final_chips')}, "
        f"Quit: {player.get('quit')}"
    )

# --------- Run ---------
def log_env_vars():
    safe_envs = ["TELEGRAM_TOKEN", "MONGO_URL"]
    for key in safe_envs:
        val = os.getenv(key, None)
        if not val:
            logger.warning("ENV %s is missing!", key)
        else:
            # Only show first 6 characters to avoid leaking secrets
            preview = val[:6] + "..." if len(val) > 6 else val
            logger.info("ENV %s loaded = %s", key, preview)

def main():
    logger.info("Starting ChipBot...")

    # Log environment vars
    log_env_vars()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newgame", newgame))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("buyin", buyin))
    app.add_handler(CommandHandler("status", status))

    logger.info("ChipBot polling started.")
    app.run_polling()

if __name__ == "__main__":
    main()
