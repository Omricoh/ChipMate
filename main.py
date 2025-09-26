import os, logging
from pymongo import MongoClient
from bson import ObjectId

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from src.dal.games_dal import GamesDAL
from src.dal.players_dal import PlayersDAL
from src.dal.transactions_dal import TransactionsDAL
from src.bl.game_bl import create_game
from src.bl.player_bl import join_game
from src.bl.transaction_bl import create_buyin, create_cashout

# ENV
TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chipbot")

# DB + DAL
client = MongoClient(MONGO_URL)
db = client["chipbot"]
game_dal = GamesDAL(db)
player_dal = PlayersDAL(db)
transaction_dal = TransactionsDAL(db)

# Keyboards
PLAYER_MENU = ReplyKeyboardMarkup(
    [
        ["💰 Buy-in", "💸 Cashout"],
        ["🎲 Chips", "🚪 Quit"],
        ["📊 Status"]
    ],
    resize_keyboard=True,
)

HOST_MENU = ReplyKeyboardMarkup(
    [
        ["👤 Player List", "🔚 End Game"],
        ["⚖️ Settle", "📊 Status"]
    ],
    resize_keyboard=True,
)

# Conversations states
ASK_BUYIN_TYPE, ASK_BUYIN_AMOUNT = range(2)
ASK_CASHOUT = range(1)
ASK_CHIPS = range(1)
ASK_QUIT_CONFIRM = range(1)
ASK_END_GAME_CONFIRM = range(1)

# -------- Helpers --------
def get_active_game(user_id: int):
    return player_dal.get_active(user_id)

def get_host_id(game_id: str):
    g = db.games.find_one({"_id": ObjectId(game_id)})
    return g.get("host_id") if g else None

# -------- Commands --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎲 ChipBot ready! Use /newgame to start.")

async def newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    host = update.effective_user
    game, host_player = create_game(host.id, host.first_name)
    gid = game_dal.create(game)
    host_player.game_id = gid
    player_dal.upsert(host_player)
    await update.message.reply_text(f"🎮 Game created with code {game.code}", reply_markup=HOST_MENU)

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /join <game_code>")
        return
    code = context.args[0].upper()
    game = game_dal.get_by_code(code)
    if not game:
        await update.message.reply_text("⚠️ Game not found or inactive.")
        return
    gid = str(game["_id"])
    user = update.effective_user
    player = join_game(gid, user.id, user.first_name)
    player_dal.upsert(player)
    game_dal.add_player(game["_id"], user.id)
    await update.message.reply_text(f"{user.first_name} joined game {code} ✅", reply_markup=PLAYER_MENU)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    if not pdoc:
        await update.message.reply_text("⚠️ You are not in an active game.")
        return
    await update.message.reply_text(
        f"📊 Game status\nBuyins: {pdoc.get('buyins', [])}\nFinal Chips: {pdoc.get('final_chips')}\nQuit: {pdoc.get('quit')}"
    )

# -------- Buy-in conversation --------
async def buyin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [["💰 Cash", "💳 Register"]]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("How do you want to buy in?", reply_markup=markup)
    return ASK_BUYIN_TYPE

async def buyin_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data["buy_type"] = "cash" if "Cash" in text else "register"
    await update.message.reply_text("Enter amount of chips:")
    return ASK_BUYIN_AMOUNT

async def buyin_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Enter a valid number.")
        return ASK_BUYIN_AMOUNT
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    gid = pdoc["game_id"]
    tx = create_buyin(gid, user.id, context.user_data["buy_type"], amount)
    res = transaction_dal.create(tx)
    await update.message.reply_text(f"✅ Buy-in {context.user_data['buy_type']} {amount} submitted.", reply_markup=PLAYER_MENU)
    host_id = get_host_id(gid)
    if host_id:
        buttons = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{res.inserted_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{res.inserted_id}")
        ]]
        await context.bot.send_message(chat_id=host_id, text=f"📢 {user.first_name} requests {context.user_data['buy_type']} {amount}", reply_markup=InlineKeyboardMarkup(buttons))
    return ConversationHandler.END

# -------- Cashout conversation --------
async def cashout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💸 Enter chip count to cash out:")
    return ASK_CASHOUT

async def cashout_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Enter a valid number.")
        return ASK_CASHOUT
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    gid = pdoc["game_id"]
    tx = create_cashout(gid, user.id, amount)
    res = transaction_dal.create(tx)
    await update.message.reply_text(f"✅ Cashout {amount} submitted.", reply_markup=PLAYER_MENU)
    host_id = get_host_id(gid)
    if host_id:
        buttons = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{res.inserted_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{res.inserted_id}")
        ]]
        await context.bot.send_message(chat_id=host_id, text=f"📢 {user.first_name} requests cashout {amount}", reply_markup=InlineKeyboardMarkup(buttons))
    return ConversationHandler.END

# -------- Chips conversation --------
async def chips_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎲 Enter your final chip count:")
    return ASK_CHIPS

async def chips_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chips = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Enter a valid number.")
        return ASK_CHIPS
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    db.players.update_one({"game_id": pdoc["game_id"], "user_id": user.id}, {"$set": {"final_chips": chips}})
    await update.message.reply_text(f"✅ Final chip count = {chips}", reply_markup=PLAYER_MENU)
    host_id = get_host_id(pdoc["game_id"])
    if host_id:
        await context.bot.send_message(chat_id=host_id, text=f"📢 {user.first_name} submitted final chips = {chips}")
    return ConversationHandler.END

# -------- Quit conversation --------
async def quit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [["✅ Yes, Quit", "❌ No"]]
    await update.message.reply_text("🚪 Quit game?", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True))
    return ASK_QUIT_CONFIRM

async def quit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    if "Yes" in text:
        db.players.update_one({"game_id": pdoc["game_id"], "user_id": user.id}, {"$set": {"quit": True, "active": False}})
        await update.message.reply_text("✅ You quit the game.", reply_markup=PLAYER_MENU)
        host_id = get_host_id(pdoc["game_id"])
        if host_id:
            await context.bot.send_message(chat_id=host_id, text=f"📢 {user.first_name} quit the game.")
    else:
        await update.message.reply_text("❌ Still in game.", reply_markup=PLAYER_MENU)
    return ConversationHandler.END

# -------- Host menu functions --------
async def player_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of players in the game"""
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    if not pdoc or not pdoc.get("is_host"):
        await update.message.reply_text("⚠️ Only hosts can view player list.")
        return

    game_id = pdoc["game_id"]
    players = player_dal.get_players(game_id)
    if not players:
        await update.message.reply_text("No players in the game yet.")
        return

    msg = "👥 **Players in game:**\n\n"
    for p in players:
        status = "🚪 Quit" if p.quit else "✅ Active"
        chips = f"Chips: {p.final_chips}" if p.final_chips else "Chips: Not submitted"
        buyins = f"Buy-ins: {sum(p.buyins)}" if p.buyins else "Buy-ins: 0"
        msg += f"• {p.name} ({status})\n  {buyins}, {chips}\n"

    await update.message.reply_text(msg, reply_markup=HOST_MENU)

async def end_game_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start end game process"""
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    if not pdoc or not pdoc.get("is_host"):
        await update.message.reply_text("⚠️ Only hosts can end the game.")
        return

    buttons = [["✅ Yes, End Game", "❌ Cancel"]]
    await update.message.reply_text(
        "🔚 Are you sure you want to end the game? Players won't be able to submit more transactions.",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    )
    return ASK_END_GAME_CONFIRM

async def end_game_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm ending the game"""
    text = update.message.text
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)

    if "Yes" in text:
        game_id = pdoc["game_id"]
        game_dal.update_status(ObjectId(game_id), "ended")

        # Notify all players
        players = player_dal.get_players(game_id)
        for p in players:
            if p.user_id != user.id:
                try:
                    await context.bot.send_message(
                        chat_id=p.user_id,
                        text="🔚 The game has been ended by the host. Please submit your final chip count if you haven't."
                    )
                except:
                    pass

        await update.message.reply_text("✅ Game ended. You can now settle accounts.", reply_markup=HOST_MENU)
    else:
        await update.message.reply_text("❌ Game continues.", reply_markup=HOST_MENU)

    return ConversationHandler.END

async def settle_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calculate and show settlement"""
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    if not pdoc or not pdoc.get("is_host"):
        await update.message.reply_text("⚠️ Only hosts can settle the game.")
        return

    game_id = pdoc["game_id"]
    players = player_dal.get_players(game_id)

    # Calculate net position for each player
    settlements = []
    for p in players:
        if p.quit or not p.active:
            continue

        # Get all confirmed transactions
        total_buyins = sum(p.buyins) if p.buyins else 0
        final_chips = p.final_chips if p.final_chips is not None else 0
        net = final_chips - total_buyins

        settlements.append({
            "name": p.name,
            "buyins": total_buyins,
            "chips": final_chips,
            "net": net
        })

    if not settlements:
        await update.message.reply_text("No active players to settle.")
        return

    # Sort by net position
    settlements.sort(key=lambda x: x["net"], reverse=True)

    msg = "💰 **Settlement Summary:**\n\n"
    for s in settlements:
        symbol = "🟢" if s["net"] > 0 else "🔴" if s["net"] < 0 else "⚪"
        msg += f"{symbol} {s['name']}\n"
        msg += f"  Buy-ins: {s['buyins']}\n"
        msg += f"  Final: {s['chips']}\n"
        msg += f"  Net: {'+' if s['net'] > 0 else ''}{s['net']}\n\n"

    # Calculate who owes whom
    msg += "**Payments:**\n"
    winners = [s for s in settlements if s["net"] > 0]
    losers = [s for s in settlements if s["net"] < 0]

    for loser in losers:
        debt = abs(loser["net"])
        for winner in winners:
            if debt <= 0:
                break
            if winner["net"] <= 0:
                continue

            payment = min(debt, winner["net"])
            msg += f"• {loser['name']} → {winner['name']}: {payment}\n"
            debt -= payment
            winner["net"] -= payment

    await update.message.reply_text(msg, reply_markup=HOST_MENU)

async def host_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive game status for hosts"""
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)

    if pdoc and pdoc.get("is_host"):
        game_id = pdoc["game_id"]
        game = game_dal.get_game(game_id)
        players = player_dal.get_players(game_id)

        active_players = sum(1 for p in players if p.active and not p.quit)
        total_buyins = sum(sum(p.buyins) if p.buyins else 0 for p in players)

        msg = f"📊 **Game Status**\n\n"
        msg += f"Code: {game.code}\n"
        msg += f"Status: {game.status}\n"
        msg += f"Players: {active_players} active\n"
        msg += f"Total buy-ins: {total_buyins}\n"

        await update.message.reply_text(msg, reply_markup=HOST_MENU)
    else:
        # Regular player status
        await status(update, context)

# -------- Inline approvals --------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, tx_id = query.data.split(":")
    tx = transaction_dal.get(ObjectId(tx_id))
    if not tx:
        await query.edit_message_text("⚠️ Transaction not found")
        return
    if action == "approve":
        transaction_dal.update_status(ObjectId(tx_id), True, False)
        await query.edit_message_text(f"✅ Approved {tx['type']} {tx['amount']}")
        await context.bot.send_message(chat_id=tx["user_id"], text=f"✅ Approved {tx['type']} {tx['amount']}")
    else:
        transaction_dal.update_status(ObjectId(tx_id), False, True)
        await query.edit_message_text(f"❌ Rejected {tx['type']} {tx['amount']}")
        await context.bot.send_message(chat_id=tx["user_id"], text=f"❌ Rejected {tx['type']} {tx['amount']}")

# -------- Main --------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newgame", newgame))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("status", status))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Buy-in$"), buyin_start)],
        states={ASK_BUYIN_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buyin_type)],
                ASK_BUYIN_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buyin_amount)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Cashout$"), cashout_start)],
        states={ASK_CASHOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cashout_amount)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎲 Chips$"), chips_start)],
        states={ASK_CHIPS: [MessageHandler(filters.TEXT & ~filters.COMMAND, chips_amount)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🚪 Quit$"), quit_start)],
        states={ASK_QUIT_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, quit_confirm)]},
        fallbacks=[]
    ))

    # Host menu handlers
    app.add_handler(MessageHandler(filters.Regex("^👤 Player List$"), player_list))
    app.add_handler(MessageHandler(filters.Regex("^⚖️ Settle$"), settle_game))
    app.add_handler(MessageHandler(filters.Regex("^📊 Status$"), host_status))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔚 End Game$"), end_game_start)],
        states={ASK_END_GAME_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, end_game_confirm)]},
        fallbacks=[]
    ))

    app.add_handler(CallbackQueryHandler(handle_callback))
    logger.info("ChipBot started polling")
    app.run_polling()

if __name__ == "__main__":
    main()
