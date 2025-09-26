import os
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pymongo import MongoClient

TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")

client = MongoClient(MONGO_URL)
db = client["chipbot"]

# ---------------- Commands ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.message.reply_text(
        f"New game started by {host.first_name}! 🎮\nGame ID: {gid}\nPlayers can join with /join {gid}"
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
    await update.message.reply_text(
        f"Buy-in request: {buy_type} {amount} chips (waiting host confirm)."
    )

# ---------------- Run ----------------

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newgame", newgame))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("buyin", buyin))

    app.run_polling()

if __name__ == "__main__":
    main()
