import os, logging, asyncio, re
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
from src.models.game import Game
from src.models.player import Player
from src.models.transaction import Transaction
from src.bl.game_bl import create_game
from src.bl.player_bl import join_game
from src.bl.transaction_bl import create_buyin, create_cashout

# ENV
TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("chipbot")

# Reduce noise from httpx and telegram libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

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
        ["📊 Status", "❓ Help"]
    ],
    resize_keyboard=True,
)

HOST_MENU = ReplyKeyboardMarkup(
    [
        ["👤 Player List", "🔚 End Game"],
        ["💰 Host Buy-in", "💸 Host Cashout"],
        ["⚖️ Settle", "📊 Status"],
        ["❓ Help"]
    ],
    resize_keyboard=True,
)

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["🎮 Manage Active Games", "📋 List All Games"],
        ["⏰ Expire Old Games", "📊 Game Report"],
        ["🔍 Find Game", "❓ Help"],
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
ADMIN_MODE, ASK_GAME_CODE_REPORT, ADMIN_MANAGE_GAME, ADMIN_SELECT_GAME = range(4)

# -------- Helpers --------
def get_active_game(user_id: int):
    return player_dal.get_active(user_id)

def get_host_id(game_id: str):
    g = db.games.find_one({"_id": ObjectId(game_id)})
    return g.get("host_id") if g else None

# -------- Commands --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎲 **ChipBot Ready!**\n\n"
        "Commands (no / needed):\n"
        "• `newgame` - Create a new game\n"
        "• `join ABC12` - Join a game\n"
        "• `status` - Check your current game\n"
        "• `mygame` - Quick game info\n"
        "• `/admin user pass` - Admin access",
        parse_mode="Markdown"
    )

async def mygame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick command to show current game info"""
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)

    if not pdoc:
        await update.message.reply_text("❌ You are not in any active game.\n\n• /newgame - Create game\n• /join <code> - Join game")
        return

    game = game_dal.get_game(pdoc["game_id"])
    if not game:
        await update.message.reply_text("⚠️ Game data not found.")
        return

    is_host = pdoc.get("is_host", False)
    menu = HOST_MENU if is_host else PLAYER_MENU

    msg = f"🎮 **Your Current Game**\n\n"
    msg += f"Code: **{game.code}**\n"
    msg += f"You are: {'🎩 Host' if is_host else '🎮 Player'}"

    await update.message.reply_text(msg, reply_markup=menu, parse_mode="Markdown")

# -------- Help functions --------
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show context-sensitive help"""
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)

    if not pdoc:
        # No active game - show general help
        await update.message.reply_text(
            "❓ **ChipBot Help**\n\n"
            "**Getting Started:**\n"
            "• `newgame` - Create a new poker game\n"
            "• `join ABC12` - Join a game with code\n"
            "• `status` - Check your current game\n"
            "• `mygame` - Quick game overview\n\n"
            "**Note:** No forward slashes (/) needed!",
            parse_mode="Markdown"
        )
        return

    is_host = pdoc.get("is_host", False)

    if is_host:
        # Host help
        await update.message.reply_text(
            "❓ **Host Menu Help**\n\n"
            "**Player Management:**\n"
            "• `👤 Player List` - View all players and their status\n\n"
            "**Transactions:**\n"
            "• `💰 Host Buy-in` - Add buy-in for any player\n"
            "• `💸 Host Cashout` - Add cashout for any player\n\n"
            "**Game Control:**\n"
            "• `⚖️ Settle` - Calculate final settlements\n"
            "• `🔚 End Game` - End the game permanently\n"
            "• `📊 Status` - View comprehensive game status\n\n"
            "**Commands:**\n"
            "• `status` - Quick status check\n"
            "• `mygame` - Game overview",
            reply_markup=HOST_MENU,
            parse_mode="Markdown"
        )
    else:
        # Player help
        await update.message.reply_text(
            "❓ **Player Menu Help**\n\n"
            "**Money Management:**\n"
            "• `💰 Buy-in` - Request buy-in (cash/register)\n"
            "• `💸 Cashout` - Request cashout\n\n"
            "**Game Actions:**\n"
            "• `🎲 Chips` - Submit your final chip count\n"
            "• `🚪 Quit` - Leave the game\n"
            "• `📊 Status` - View your game status\n\n"
            "**Commands:**\n"
            "• `status` - Quick status check\n"
            "• `mygame` - Game overview\n\n"
            "**Note:** Host must approve buy-ins/cashouts!",
            reply_markup=PLAYER_MENU,
            parse_mode="Markdown"
        )

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin help"""
    await update.message.reply_text(
        "❓ **Admin Menu Help**\n\n"
        "**Game Management:**\n"
        "• `🎮 Manage Active Games` - Take control of any game\n"
        "• `📋 List All Games` - View all games with status\n"
        "• `⏰ Expire Old Games` - Expire games older than 12h\n\n"
        "**Reporting:**\n"
        "• `📊 Game Report` - Detailed game analysis\n"
        "• `🔍 Find Game` - Search for games\n\n"
        "**Access:**\n"
        "• `admin username password` - Login to admin\n"
        "• `🚪 Exit Admin` - Leave admin mode",
        reply_markup=ADMIN_MENU,
        parse_mode="Markdown"
    )

async def newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    host = update.effective_user

    # Check if user is already in an active game
    existing = player_dal.get_active(host.id)
    if existing:
        existing_game = game_dal.get_game(existing["game_id"])
        if existing_game:
            await update.message.reply_text(
                f"❌ You are already in an active game (Code: {existing_game.code})\n\n"
                f"You must quit your current game before creating a new one."
            )
            return

    game, host_player = create_game(host.id, host.first_name)
    gid = game_dal.create(game)
    host_player.game_id = gid
    player_dal.upsert(host_player)
    await update.message.reply_text(f"🎮 Game created with code {game.code}", reply_markup=HOST_MENU)

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /join <game_code>")
        return

    user = update.effective_user

    # Check if user is already in an active game
    existing = player_dal.get_active(user.id)
    if existing:
        existing_game = game_dal.get_game(existing["game_id"])
        if existing_game:
            await update.message.reply_text(
                f"❌ You are already in an active game (Code: {existing_game.code})\n\n"
                f"You must quit your current game before joining another one.\n"
                f"Use the '🚪 Quit' button in your current game menu."
            )
            # Show their current game menu based on role
            if existing.get("is_host"):
                await update.message.reply_text("Returning to your host menu...", reply_markup=HOST_MENU)
            else:
                await update.message.reply_text("Returning to your player menu...", reply_markup=PLAYER_MENU)
            return

    code = context.args[0].upper()
    game_doc = db.games.find_one({"code": code, "status": "active"})
    if not game_doc:
        await update.message.reply_text("⚠️ Game not found or inactive.")
        return

    # Check if game has expired
    game = Game(**game_doc)
    if (datetime.utcnow() - game.created_at) > timedelta(hours=12):
        await update.message.reply_text("⚠️ This game has expired (older than 12 hours).")
        return

    gid = str(game_doc["_id"])

    # Check if user is the host trying to rejoin their own game
    if user.id == game.host_id:
        await update.message.reply_text(
            f"✅ Welcome back to your game, {user.first_name}!",
            reply_markup=HOST_MENU
        )
        # Make sure they're marked as active
        player_dal.col.update_one(
            {"game_id": gid, "user_id": user.id},
            {"$set": {"active": True, "quit": False}}
        )
        return

    # Create new player
    player = join_game(gid, user.id, user.first_name)
    player_dal.upsert(player)
    game_dal.add_player(game_doc["_id"], user.id)

    await update.message.reply_text(f"{user.first_name} joined game {code} ✅", reply_markup=PLAYER_MENU)

async def join_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'join CODE' text command"""
    text = update.message.text.strip()
    parts = text.split()

    if len(parts) != 2:
        await update.message.reply_text("Usage: `join CODE`\nExample: `join ABC12`", parse_mode="Markdown")
        return

    # Set up context like CommandHandler does
    context.args = [parts[1]]

    # Call the regular join function
    await join(update, context)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    if not pdoc:
        await update.message.reply_text("⚠️ You are not in an active game.\n\nUse /newgame to create or /join <code> to join.")
        return

    game = game_dal.get_game(pdoc["game_id"])
    if not game:
        await update.message.reply_text("⚠️ Game data not found.")
        return

    # Show appropriate menu based on role
    is_host = pdoc.get("is_host", False)
    menu = HOST_MENU if is_host else PLAYER_MENU

    # Calculate cash and credit buyins separately from transactions
    cash_buyins = 0
    credit_buyins = 0

    # Get all confirmed buyin transactions for this player in this game
    from src.dal.transactions_dal import TransactionsDAL
    transaction_dal_temp = TransactionsDAL(db)
    transactions = transaction_dal_temp.col.find({
        "game_id": pdoc["game_id"],
        "user_id": user.id,
        "confirmed": True,
        "rejected": False,
        "type": {"$in": ["buyin_cash", "buyin_register"]}
    })

    for tx in transactions:
        if tx["type"] == "buyin_cash":
            cash_buyins += tx["amount"]
        elif tx["type"] == "buyin_register":
            credit_buyins += tx["amount"]

    msg = f"📊 **Your Game Status**\n\n"
    msg += f"Game Code: **{game.code}**\n"
    msg += f"Cash Buy-ins: {cash_buyins}\n"
    msg += f"Credit Buy-ins: {credit_buyins}\n"
    msg += f"Status: {'🚪 Quit' if pdoc.get('quit') else '✅ Active'}"

    await update.message.reply_text(msg, reply_markup=menu, parse_mode="Markdown")

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
    tx_id = transaction_dal.create(tx)
    await update.message.reply_text(f"✅ Buy-in {context.user_data['buy_type']} {amount} submitted.", reply_markup=PLAYER_MENU)
    host_id = get_host_id(gid)
    if host_id:
        buttons = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{tx_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{tx_id}")
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
    tx_id = transaction_dal.create(tx)
    await update.message.reply_text(f"✅ Cashout {amount} submitted.", reply_markup=PLAYER_MENU)
    host_id = get_host_id(gid)
    if host_id:
        buttons = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{tx_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{tx_id}")
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

    # Check if this is admin override
    is_admin = context.user_data.get("admin_override", False)

    if is_admin:
        # Return to admin game management menu
        ADMIN_GAME_MENU = ReplyKeyboardMarkup(
            [
                ["👤 View Players", "💰 Add Buy-in"],
                ["💸 Add Cashout", "📊 Game Status"],
                ["⚖️ Settle Game", "🔚 End Game"],
                ["🔙 Back to Games List"]
            ],
            resize_keyboard=True
        )

        await update.message.reply_text(
            f"✅ Admin added buy-in:\n"
            f"Player: {player_name}\n"
            f"Type: {buy_type}\n"
            f"Amount: {amount} chips",
            reply_markup=ADMIN_GAME_MENU
        )

        # Notify the player
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=f"✅ Administrator recorded a {buy_type} buy-in of {amount} chips for you."
            )
        except:
            pass

        context.user_data["admin_override"] = False
        return ADMIN_MANAGE_GAME
    else:
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
            pass

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

    # Check if this is admin override
    is_admin = context.user_data.get("admin_override", False)

    if is_admin:
        # Return to admin game management menu
        ADMIN_GAME_MENU = ReplyKeyboardMarkup(
            [
                ["👤 View Players", "💰 Add Buy-in"],
                ["💸 Add Cashout", "📊 Game Status"],
                ["⚖️ Settle Game", "🔚 End Game"],
                ["🔙 Back to Games List"]
            ],
            resize_keyboard=True
        )

        await update.message.reply_text(
            f"✅ Admin added cashout:\n"
            f"Player: {player_name}\n"
            f"Amount: {amount} chips",
            reply_markup=ADMIN_GAME_MENU
        )

        # Notify the player
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=f"✅ Administrator recorded a cashout of {amount} chips for you."
            )
        except:
            pass

        context.user_data["admin_override"] = False
        return ADMIN_MANAGE_GAME
    else:
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
            pass

        return ConversationHandler.END

# -------- Admin functions --------
async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin login command"""
    if not context.args or len(context.args) != 2:
        await update.message.reply_text(
            "🔐 **Admin Login Required**\n\n"
            "Usage: `/admin <username> <password>`\n\n"
            "Example: `/admin admin secret123`\n\n"
            "Note: Admin credentials must be set in environment variables.",
            parse_mode="Markdown"
        )
        return

    username, password = context.args[0], context.args[1]

    # Verify admin credentials
    admin_user = os.getenv("ADMIN_USER")
    admin_pass = os.getenv("ADMIN_PASS")

    if admin_user and admin_pass:
        if username != admin_user or password != admin_pass:
            await update.message.reply_text("❌ Invalid admin credentials")
            return
    else:
        # If no credentials are set in environment, allow any login (for testing)
        await update.message.reply_text(
            "⚠️ Warning: No admin credentials set in environment.\n"
            "Allowing access for testing purposes."
        )

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

async def admin_text_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'admin user pass' text command"""
    text = update.message.text.strip()
    parts = text.split()

    if len(parts) != 3:
        await update.message.reply_text(
            "🔐 **Admin Login Required**\n\n"
            "Usage: `admin <username> <password>`\n\n"
            "Example: `admin admin secret123`",
            parse_mode="Markdown"
        )
        return

    # Set up context like CommandHandler does
    context.args = [parts[1], parts[2]]

    # Call the regular admin_login function
    return await admin_login(update, context)

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

async def admin_manage_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active games for admin to manage"""
    if not context.user_data.get("admin_auth"):
        await update.message.reply_text("⚠️ Admin authentication required")
        return ADMIN_MODE

    try:
        games = game_dal.list_games(
            user=context.user_data.get("admin_user"),
            password=context.user_data.get("admin_pass")
        )

        active_games = [g for g in games if g.status == "active"]

        if not active_games:
            await update.message.reply_text("No active games to manage.", reply_markup=ADMIN_MENU)
            return ADMIN_MODE

        # Create buttons for each active game
        buttons = []
        context.user_data["admin_active_games"] = {}

        for game in active_games:
            game_id = str(game_dal.col.find_one({"code": game.code})["_id"])
            context.user_data["admin_active_games"][game.code] = game_id

            # Get player count
            player_count = len(player_dal.get_players(game_id))

            button_text = f"{game.code} - {game.host_name} ({player_count} players)"
            buttons.append([button_text])

        buttons.append(["🔙 Back to Admin Menu"])

        markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        await update.message.reply_text(
            "🎮 **Select a game to manage:**\n\n"
            "You can manage any active game as if you were the host.",
            reply_markup=markup
        )

        return ADMIN_SELECT_GAME

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}", reply_markup=ADMIN_MENU)
        return ADMIN_MODE

async def admin_select_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle game selection for admin management"""
    text = update.message.text

    if "Back to Admin Menu" in text:
        await update.message.reply_text("Returning to admin menu...", reply_markup=ADMIN_MENU)
        return ADMIN_MODE

    # Extract game code from button text
    code = text.split(" - ")[0] if " - " in text else None

    if not code or code not in context.user_data.get("admin_active_games", {}):
        await update.message.reply_text("Invalid selection. Please try again.")
        return ADMIN_SELECT_GAME

    game_id = context.user_data["admin_active_games"][code]
    context.user_data["admin_managing_game"] = game_id
    context.user_data["admin_managing_code"] = code

    # Create admin game management menu
    ADMIN_GAME_MENU = ReplyKeyboardMarkup(
        [
            ["👤 View Players", "💰 Add Buy-in"],
            ["💸 Add Cashout", "📊 Game Status"],
            ["⚖️ Settle Game", "🔚 End Game"],
            ["🔙 Back to Games List"]
        ],
        resize_keyboard=True
    )

    await update.message.reply_text(
        f"📌 **Managing Game: {code}**\n\n"
        f"Select an action:",
        reply_markup=ADMIN_GAME_MENU
    )

    return ADMIN_MANAGE_GAME

async def admin_manage_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin game management actions"""
    text = update.message.text
    game_id = context.user_data.get("admin_managing_game")
    code = context.user_data.get("admin_managing_code")

    if not game_id:
        await update.message.reply_text("No game selected.", reply_markup=ADMIN_MENU)
        return ADMIN_MODE

    if "Back to Games List" in text:
        return await admin_manage_games(update, context)

    elif "View Players" in text:
        players = player_dal.get_players(game_id)
        if not players:
            await update.message.reply_text("No players in this game.")
            return ADMIN_MANAGE_GAME

        msg = f"👥 **Players in {code}:**\n\n"
        for p in players:
            status = "🚪 Quit" if p.quit else "✅ Active"
            chips = f"Chips: {p.final_chips}" if p.final_chips else "Chips: Not submitted"
            buyins = f"Buy-ins: {sum(p.buyins)}" if p.buyins else "Buy-ins: 0"
            msg += f"• {p.name} (ID: {p.user_id}) {status}\n"
            msg += f"  {buyins}, {chips}\n\n"

        await update.message.reply_text(msg)
        return ADMIN_MANAGE_GAME

    elif "Add Buy-in" in text:
        # Temporarily set admin as host for this game in context
        context.user_data["admin_override"] = True
        context.user_data["game_id"] = game_id
        return await admin_buyin_for_player(update, context)

    elif "Add Cashout" in text:
        context.user_data["admin_override"] = True
        context.user_data["game_id"] = game_id
        return await admin_cashout_for_player(update, context)

    elif "Game Status" in text:
        game = game_dal.get_game(game_id)
        players = player_dal.get_players(game_id)

        active_players = sum(1 for p in players if p.active and not p.quit)
        total_buyins = sum(sum(p.buyins) if p.buyins else 0 for p in players)

        msg = f"📊 **Game Status: {code}**\n\n"
        msg += f"Host: {game.host_name}\n"
        msg += f"Status: {game.status}\n"
        msg += f"Players: {active_players} active\n"
        msg += f"Total buy-ins: {total_buyins}\n"
        msg += f"Created: {game.created_at.strftime('%Y-%m-%d %H:%M')}\n"

        await update.message.reply_text(msg)
        return ADMIN_MANAGE_GAME

    elif "Settle Game" in text:
        return await admin_settle_game(update, context, game_id)

    elif "End Game" in text:
        game_dal.update_status(game_id, "ended")

        # Notify all players
        players = player_dal.get_players(game_id)
        for p in players:
            try:
                await context.bot.send_message(
                    chat_id=p.user_id,
                    text=f"🔚 Game {code} has been ended by an administrator."
                )
            except:
                pass

        await update.message.reply_text(f"✅ Game {code} has been ended.", reply_markup=ADMIN_MENU)
        return ADMIN_MODE

    else:
        await update.message.reply_text("Unknown action.")
        return ADMIN_MANAGE_GAME

async def admin_buyin_for_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin adds buy-in for any player"""
    game_id = context.user_data.get("game_id")
    players = player_dal.get_players(game_id)

    if not players:
        await update.message.reply_text("No players in the game.")
        return ADMIN_MANAGE_GAME

    buttons = []
    for p in players:
        if p.active and not p.quit:
            buttons.append([f"{p.name} (ID: {p.user_id})"])

    buttons.append(["❌ Cancel"])
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text("Select player to add buy-in:", reply_markup=markup)
    context.user_data["admin_action"] = "buyin"
    return ASK_HOST_BUYIN_PLAYER

async def admin_cashout_for_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin adds cashout for any player"""
    game_id = context.user_data.get("game_id")
    players = player_dal.get_players(game_id)

    if not players:
        await update.message.reply_text("No players in the game.")
        return ADMIN_MANAGE_GAME

    buttons = []
    for p in players:
        if p.active and not p.quit:
            buttons.append([f"{p.name} (ID: {p.user_id})"])

    buttons.append(["❌ Cancel"])
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text("Select player to add cashout:", reply_markup=markup)
    context.user_data["admin_action"] = "cashout"
    return ASK_HOST_CASHOUT_PLAYER

async def admin_settle_game(update: Update, context: ContextTypes.DEFAULT_TYPE, game_id):
    """Admin settles the game"""
    players = player_dal.get_players(game_id)

    # Calculate net position for each player
    settlements = []
    for p in players:
        if p.quit or not p.active:
            continue

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
        return ADMIN_MANAGE_GAME

    # Sort by net position
    settlements.sort(key=lambda x: x["net"], reverse=True)

    msg = f"💰 **Settlement for {context.user_data.get('admin_managing_code')}:**\n\n"
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

    await update.message.reply_text(msg)
    return ADMIN_MANAGE_GAME

async def admin_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin menu selections"""
    text = update.message.text

    if "Manage Active Games" in text:
        return await admin_manage_games(update, context)
    elif "List All Games" in text:
        return await admin_list_all_games(update, context)
    elif "Expire Old Games" in text:
        return await admin_expire_games(update, context)
    elif "Game Report" in text:
        return await admin_game_report_ask(update, context)
    elif "Find Game" in text:
        return await admin_find_game(update, context)
    elif "Help" in text:
        await admin_help(update, context)
        return ADMIN_MODE
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
    # Check for required token
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return

    logger.info(f"Starting ChipBot...")
    logger.info(f"MongoDB: {MONGO_URL}")

    # Build application
    app = Application.builder().token(TOKEN).build()

    # Schedule background task to run every hour (if job queue is available)
    try:
        job_queue = app.job_queue
        if job_queue:
            job_queue.run_repeating(expire_games_task, interval=3600, first=10)
            logger.info("Background task scheduled to expire games every hour")
        else:
            logger.warning("JobQueue not available. Install with: pip install 'python-telegram-bot[job-queue]'")
            logger.warning("Games will not automatically expire after 12 hours. Use admin menu to manually expire.")
    except Exception as e:
        logger.warning(f"Could not set up job queue: {e}")
        logger.warning("Games will not automatically expire. Use admin menu to manually expire.")
    # Command handlers - accept both /command and plain text
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^start$"), start))

    app.add_handler(CommandHandler("newgame", newgame))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^newgame$"), newgame))

    app.add_handler(CommandHandler("join", join))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^join\s+\w+$"), join_text))

    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^status$"), status))

    app.add_handler(CommandHandler("mygame", mygame))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^mygame$"), mygame))

    # Help handlers
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^help$"), help_handler))
    app.add_handler(MessageHandler(filters.Regex("^❓ Help$"), help_handler))

    # Admin conversation handler
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin_login),
            MessageHandler(filters.Regex(r"(?i)^admin\s+\w+\s+\w+$"), admin_text_login)
        ],
        states={
            ADMIN_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_mode_handler)],
            ASK_GAME_CODE_REPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_game_report)],
            ADMIN_SELECT_GAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_select_game)],
            ADMIN_MANAGE_GAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_manage_game_handler)]
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

    # Start the bot
    logger.info("ChipBot starting polling...")
    try:
        app.run_polling(drop_pending_updates=True, close_loop=False)
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        logger.info("ChipBot shutting down...")

if __name__ == "__main__":
    import signal
    import sys

    def signal_handler(sig, frame):
        logger.info("Received interrupt signal, shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    main()
