import os, logging, asyncio
from datetime import datetime, timedelta
from pymongo import MongoClient
from bson import ObjectId

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
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
        ["💰 Host Buy-in", "💸 Host Cashout"],
        ["⚖️ Settle", "📊 Status"]
    ],
    resize_keyboard=True,
)

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["📋 List All Games", "⏰ Expire Old Games"],
        ["📊 Game Report", "🔍 Find Game"],
        ["🚪 Exit Admin"]
    ],
    resize_keyboard=True,
)

# Conversations states
ASK_BUYIN_TYPE, ASK_BUYIN_AMOUNT = range(2)
ASK_CASHOUT = range(1)
ASK_CHIPS = range(1)
ASK_QUIT_CONFIRM = range(1)
ASK_END_GAME_CONFIRM = range(1)
ASK_HOST_BUYIN_PLAYER, ASK_HOST_BUYIN_TYPE, ASK_HOST_BUYIN_AMOUNT = range(3)
ASK_HOST_CASHOUT_PLAYER, ASK_HOST_CASHOUT_AMOUNT = range(2)
ADMIN_MODE, ASK_GAME_CODE_REPORT = range(2)

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

# -------- Host Buy-in conversation --------
async def host_buyin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Host can buy-in for any player"""
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)

    if not pdoc or not pdoc.get("is_host"):
        await update.message.reply_text("⚠️ Only hosts can use this feature.")
        return ConversationHandler.END

    game_id = pdoc["game_id"]
    players = player_dal.get_players(game_id)

    if not players:
        await update.message.reply_text("No players in the game.")
        return ConversationHandler.END

    # Create keyboard with player names
    buttons = []
    for p in players:
        if p.active and not p.quit:
            buttons.append([f"{p.name} (ID: {p.user_id})"])

    if not buttons:
        await update.message.reply_text("No active players.")
        return ConversationHandler.END

    buttons.append(["❌ Cancel"])
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text("Select player to buy-in for:", reply_markup=markup)
    context.user_data["game_id"] = game_id
    return ASK_HOST_BUYIN_PLAYER

async def host_buyin_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select which player to buy-in for"""
    text = update.message.text

    if "Cancel" in text:
        await update.message.reply_text("Cancelled.", reply_markup=HOST_MENU)
        return ConversationHandler.END

    # Extract user_id from the text
    import re
    match = re.search(r'ID: (\d+)', text)
    if not match:
        await update.message.reply_text("Invalid selection. Please try again.")
        return ASK_HOST_BUYIN_PLAYER

    player_id = int(match.group(1))
    player_name = text.split(" (ID:")[0]

    context.user_data["target_player_id"] = player_id
    context.user_data["target_player_name"] = player_name

    buttons = [["💰 Cash", "💳 Register"], ["❌ Cancel"]]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        f"Buy-in type for {player_name}:",
        reply_markup=markup
    )
    return ASK_HOST_BUYIN_TYPE

async def host_buyin_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select buy-in type"""
    text = update.message.text

    if "Cancel" in text:
        await update.message.reply_text("Cancelled.", reply_markup=HOST_MENU)
        return ConversationHandler.END

    context.user_data["buy_type"] = "cash" if "Cash" in text else "register"

    await update.message.reply_text(
        f"Enter chip amount for {context.user_data['target_player_name']}:"
    )
    return ASK_HOST_BUYIN_AMOUNT

async def host_buyin_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enter buy-in amount and process"""
    try:
        amount = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Enter a valid number:")
        return ASK_HOST_BUYIN_AMOUNT

    # Create the transaction
    game_id = context.user_data["game_id"]
    player_id = context.user_data["target_player_id"]
    player_name = context.user_data["target_player_name"]
    buy_type = context.user_data["buy_type"]

    # Create transaction
    tx = create_buyin(game_id, player_id, buy_type, amount)
    tx_id = transaction_dal.create(tx)

    # Auto-approve since host is creating it
    transaction_dal.update_status(ObjectId(tx_id), True, False)

    # Update player's buyins
    pdoc = player_dal.get_player(game_id, player_id)
    if pdoc:
        if not pdoc.buyins:
            pdoc.buyins = []
        pdoc.buyins.append(amount)
        player_dal.upsert(pdoc)

    await update.message.reply_text(
        f"✅ Buy-in recorded:\n"
        f"Player: {player_name}\n"
        f"Type: {buy_type}\n"
        f"Amount: {amount} chips",
        reply_markup=HOST_MENU
    )

    # Notify the player
    try:
        await context.bot.send_message(
            chat_id=player_id,
            text=f"✅ Host recorded a {buy_type} buy-in of {amount} chips for you."
        )
    except:
        pass  # Player might have blocked the bot

    return ConversationHandler.END

# -------- Host Cashout conversation --------
async def host_cashout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Host can cashout for any player"""
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)

    if not pdoc or not pdoc.get("is_host"):
        await update.message.reply_text("⚠️ Only hosts can use this feature.")
        return ConversationHandler.END

    game_id = pdoc["game_id"]
    players = player_dal.get_players(game_id)

    if not players:
        await update.message.reply_text("No players in the game.")
        return ConversationHandler.END

    # Create keyboard with player names
    buttons = []
    for p in players:
        if p.active and not p.quit:
            buttons.append([f"{p.name} (ID: {p.user_id})"])

    if not buttons:
        await update.message.reply_text("No active players.")
        return ConversationHandler.END

    buttons.append(["❌ Cancel"])
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text("Select player to cashout for:", reply_markup=markup)
    context.user_data["game_id"] = game_id
    return ASK_HOST_CASHOUT_PLAYER

async def host_cashout_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Select which player to cashout for"""
    text = update.message.text

    if "Cancel" in text:
        await update.message.reply_text("Cancelled.", reply_markup=HOST_MENU)
        return ConversationHandler.END

    # Extract user_id from the text
    import re
    match = re.search(r'ID: (\d+)', text)
    if not match:
        await update.message.reply_text("Invalid selection. Please try again.")
        return ASK_HOST_CASHOUT_PLAYER

    player_id = int(match.group(1))
    player_name = text.split(" (ID:")[0]

    context.user_data["target_player_id"] = player_id
    context.user_data["target_player_name"] = player_name

    await update.message.reply_text(
        f"Enter cashout amount for {player_name}:"
    )
    return ASK_HOST_CASHOUT_AMOUNT

async def host_cashout_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enter cashout amount and process"""
    try:
        amount = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Enter a valid number:")
        return ASK_HOST_CASHOUT_AMOUNT

    # Create the transaction
    game_id = context.user_data["game_id"]
    player_id = context.user_data["target_player_id"]
    player_name = context.user_data["target_player_name"]

    # Create cashout transaction
    tx = create_cashout(game_id, player_id, amount)
    tx_id = transaction_dal.create(tx)

    # Auto-approve since host is creating it
    transaction_dal.update_status(ObjectId(tx_id), True, False)

    await update.message.reply_text(
        f"✅ Cashout recorded:\n"
        f"Player: {player_name}\n"
        f"Amount: {amount} chips",
        reply_markup=HOST_MENU
    )

    # Notify the player
    try:
        await context.bot.send_message(
            chat_id=player_id,
            text=f"✅ Host recorded a cashout of {amount} chips for you."
        )
    except:
        pass  # Player might have blocked the bot

    return ConversationHandler.END

# -------- Admin functions --------
async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin login command"""
    if not context.args or len(context.args) != 2:
        await update.message.reply_text("Usage: /admin <username> <password>")
        return ConversationHandler.END

    username, password = context.args[0], context.args[1]

    # Verify admin credentials
    admin_user = os.getenv("ADMIN_USER")
    admin_pass = os.getenv("ADMIN_PASS")

    if admin_user and admin_pass:
        if username != admin_user or password != admin_pass:
            await update.message.reply_text("❌ Invalid admin credentials")
            return ConversationHandler.END

    # Store admin auth in context
    context.user_data["admin_auth"] = True
    context.user_data["admin_user"] = username
    context.user_data["admin_pass"] = password

    await update.message.reply_text(
        "🔐 **Admin Mode Activated**\n\n"
        "Select an option from the menu:",
        reply_markup=ADMIN_MENU
    )
    return ADMIN_MODE

async def admin_list_all_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all games in the system"""
    if not context.user_data.get("admin_auth"):
        await update.message.reply_text("⚠️ Admin authentication required")
        return ADMIN_MODE

    try:
        games = game_dal.list_games(
            user=context.user_data.get("admin_user"),
            password=context.user_data.get("admin_pass")
        )

        if not games:
            await update.message.reply_text("No games found.", reply_markup=ADMIN_MENU)
            return ADMIN_MODE

        msg = "📋 **All Games:**\n\n"
        active_count = 0
        expired_count = 0
        ended_count = 0

        for game in games:
            status_emoji = "🟢" if game.status == "active" else "🔴" if game.status == "expired" else "🟡"
            msg += f"{status_emoji} **{game.code}**\n"
            msg += f"  Host: {game.host_name}\n"
            msg += f"  Status: {game.status}\n"
            msg += f"  Players: {len(game.players)}\n"
            msg += f"  Created: {game.created_at.strftime('%Y-%m-%d %H:%M')}\n"

            # Check if expired
            from datetime import datetime, timedelta
            if (datetime.utcnow() - game.created_at) > timedelta(hours=12) and game.status == "active":
                msg += f"  ⚠️ Should be expired!\n"

            msg += "\n"

            if game.status == "active":
                active_count += 1
            elif game.status == "expired":
                expired_count += 1
            else:
                ended_count += 1

        msg += f"\n**Summary:**\n"
        msg += f"Active: {active_count} | Expired: {expired_count} | Ended: {ended_count}"

        await update.message.reply_text(msg, reply_markup=ADMIN_MENU)
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}", reply_markup=ADMIN_MENU)

    return ADMIN_MODE

async def admin_expire_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Expire games older than 12 hours"""
    if not context.user_data.get("admin_auth"):
        await update.message.reply_text("⚠️ Admin authentication required")
        return ADMIN_MODE

    expired_count = game_dal.expire_old_games()

    await update.message.reply_text(
        f"⏰ **Game Expiration Complete**\n\n"
        f"Expired {expired_count} games older than 12 hours.",
        reply_markup=ADMIN_MENU
    )
    return ADMIN_MODE

async def admin_game_report_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for game code to generate report"""
    if not context.user_data.get("admin_auth"):
        await update.message.reply_text("⚠️ Admin authentication required")
        return ADMIN_MODE

    await update.message.reply_text(
        "Enter the game code to generate report (or 'cancel' to go back):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASK_GAME_CODE_REPORT

async def admin_game_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate detailed game report"""
    text = update.message.text

    if text.lower() == "cancel":
        await update.message.reply_text("Cancelled.", reply_markup=ADMIN_MENU)
        return ADMIN_MODE

    code = text.upper()

    # Find game by code
    game_doc = db.games.find_one({"code": code})
    if not game_doc:
        await update.message.reply_text(
            f"Game with code {code} not found. Try again or type 'cancel':"
        )
        return ASK_GAME_CODE_REPORT

    game_id = str(game_doc["_id"])
    report = game_dal.get_game_report(game_id)

    if not report:
        await update.message.reply_text("Failed to generate report.", reply_markup=ADMIN_MENU)
        return ADMIN_MODE

    game = report["game"]
    players = report["players"]
    transactions = report["transactions"]

    msg = f"📊 **Game Report: {game.code}**\n"
    msg += "=" * 30 + "\n\n"

    # Game info
    msg += f"**Game Details:**\n"
    msg += f"Host: {game.host_name} (ID: {game.host_id})\n"
    msg += f"Status: {game.status}\n"
    msg += f"Created: {game.created_at.strftime('%Y-%m-%d %H:%M')}\n"

    from datetime import datetime
    duration = datetime.utcnow() - game.created_at
    hours = int(duration.total_seconds() // 3600)
    minutes = int((duration.total_seconds() % 3600) // 60)
    msg += f"Duration: {hours}h {minutes}m\n\n"

    # Players summary
    msg += f"**Players ({len(players)}):**\n"
    for p in players:
        status = "🚪 Quit" if p.get("quit") else "✅ Active"
        total_buyins = sum(p.get("buyins", []))
        final_chips = p.get("final_chips", "Not submitted")
        msg += f"• {p['name']} ({status})\n"
        msg += f"  Buy-ins: {total_buyins}\n"
        msg += f"  Final: {final_chips}\n"
        if isinstance(final_chips, int):
            net = final_chips - total_buyins
            msg += f"  Net: {'+' if net > 0 else ''}{net}\n"

    # Transactions summary
    msg += f"\n**Transactions ({len(transactions)}):**\n"
    confirmed_buyins = sum(1 for t in transactions if t.get("type") in ["buyin_cash", "buyin_register"] and t.get("confirmed"))
    confirmed_cashouts = sum(1 for t in transactions if t.get("type") == "cashout" and t.get("confirmed"))
    rejected = sum(1 for t in transactions if t.get("rejected"))

    msg += f"Confirmed Buy-ins: {confirmed_buyins}\n"
    msg += f"Confirmed Cashouts: {confirmed_cashouts}\n"
    msg += f"Rejected: {rejected}\n"

    # Financial summary
    total_buyin_amount = sum(t.get("amount", 0) for t in transactions
                            if t.get("type") in ["buyin_cash", "buyin_register"] and t.get("confirmed"))
    total_cashout_amount = sum(t.get("amount", 0) for t in transactions
                              if t.get("type") == "cashout" and t.get("confirmed"))

    msg += f"\n**Financial Summary:**\n"
    msg += f"Total Buy-ins: {total_buyin_amount} chips\n"
    msg += f"Total Cashouts: {total_cashout_amount} chips\n"
    msg += f"Difference: {total_buyin_amount - total_cashout_amount} chips\n"

    await update.message.reply_text(msg, reply_markup=ADMIN_MENU)
    return ADMIN_MODE

async def admin_find_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Find games by various criteria"""
    if not context.user_data.get("admin_auth"):
        await update.message.reply_text("⚠️ Admin authentication required")
        return ADMIN_MODE

    # Find active and expired games
    all_games = game_dal.list_games(
        user=context.user_data.get("admin_user"),
        password=context.user_data.get("admin_pass")
    )

    active_games = [g for g in all_games if g.status == "active"]
    expired_games = [g for g in all_games if g.status == "expired"]
    recent_games = sorted(all_games, key=lambda x: x.created_at, reverse=True)[:5]

    msg = "🔍 **Game Finder**\n\n"

    msg += f"**Active Games ({len(active_games)}):**\n"
    for game in active_games[:5]:
        msg += f"• {game.code} - {game.host_name}\n"

    msg += f"\n**Recently Expired ({len(expired_games)}):**\n"
    for game in expired_games[:5]:
        msg += f"• {game.code} - {game.host_name}\n"

    msg += f"\n**Most Recent Games:**\n"
    for game in recent_games:
        msg += f"• {game.code} - {game.created_at.strftime('%m/%d %H:%M')} - {game.status}\n"

    await update.message.reply_text(msg, reply_markup=ADMIN_MENU)
    return ADMIN_MODE

async def admin_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exit admin mode"""
    context.user_data["admin_auth"] = False
    context.user_data.pop("admin_user", None)
    context.user_data.pop("admin_pass", None)

    await update.message.reply_text(
        "🚪 Admin mode deactivated.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def admin_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin menu selections"""
    text = update.message.text

    if "List All Games" in text:
        return await admin_list_all_games(update, context)
    elif "Expire Old Games" in text:
        return await admin_expire_games(update, context)
    elif "Game Report" in text:
        return await admin_game_report_ask(update, context)
    elif "Find Game" in text:
        return await admin_find_game(update, context)
    elif "Exit Admin" in text:
        return await admin_exit(update, context)
    else:
        await update.message.reply_text("Unknown command", reply_markup=ADMIN_MENU)
        return ADMIN_MODE

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

# -------- Background Tasks --------
async def expire_games_task(context: ContextTypes.DEFAULT_TYPE):
    """Background task to expire games older than 12 hours"""
    logger.info("Running game expiration task...")
    expired_count = game_dal.expire_old_games()
    if expired_count > 0:
        logger.info(f"Expired {expired_count} games")

# -------- Main --------
def main():
    app = Application.builder().token(TOKEN).build()

    # Schedule background task to run every hour
    job_queue = app.job_queue
    job_queue.run_repeating(expire_games_task, interval=3600, first=10)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newgame", newgame))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("status", status))

    # Admin conversation handler
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("admin", admin_login)],
        states={
            ADMIN_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_mode_handler)],
            ASK_GAME_CODE_REPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_game_report)]
        },
        fallbacks=[MessageHandler(filters.Regex("^🚪 Exit Admin$"), admin_exit)]
    ))

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

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Host Buy-in$"), host_buyin_start)],
        states={
            ASK_HOST_BUYIN_PLAYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, host_buyin_player)],
            ASK_HOST_BUYIN_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, host_buyin_type)],
            ASK_HOST_BUYIN_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, host_buyin_amount)]
        },
        fallbacks=[]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Host Cashout$"), host_cashout_start)],
        states={
            ASK_HOST_CASHOUT_PLAYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, host_cashout_player)],
            ASK_HOST_CASHOUT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, host_cashout_amount)]
        },
        fallbacks=[]
    ))

    app.add_handler(CallbackQueryHandler(handle_callback))
    logger.info("ChipBot started polling")
    app.run_polling()

if __name__ == "__main__":
    main()
