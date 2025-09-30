import os, logging, asyncio, re, io
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from bson import ObjectId

import qrcode
from PIL import Image

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
from src.dal.debt_dal import DebtDAL
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
debt_dal = DebtDAL(db)

# QR Code generation function
def generate_game_qr(game_code, bot_username):
    """Generate QR code for joining a game"""
    # Create Telegram bot link that auto-joins the game
    join_url = f"https://t.me/{bot_username}?start=join_{game_code}"

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(join_url)
    qr.make(fit=True)

    # Create QR code image
    qr_img = qr.make_image(fill_color="black", back_color="white")

    # Convert to BytesIO for sending
    bio = io.BytesIO()
    qr_img.save(bio, format='PNG')
    bio.seek(0)

    return bio, join_url

# Keyboards
PLAYER_MENU = ReplyKeyboardMarkup(
    [
        ["💰 Buy-in", "💸 Cashout"],
        ["🚪 Quit", "📊 Status"],
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
ASK_CASHOUT, ASK_NEW_HOST_SELECTION = range(2)
ASK_QUIT_CONFIRM = range(1)
ASK_END_GAME_CONFIRM = range(1)
ASK_HOST_BUYIN_PLAYER, ASK_HOST_BUYIN_TYPE, ASK_HOST_BUYIN_AMOUNT = range(3)
ASK_HOST_CASHOUT_PLAYER, ASK_HOST_CASHOUT_AMOUNT = range(2)
ASK_PLAYER_NAME = 0
ADMIN_MODE, ASK_GAME_CODE_REPORT, ADMIN_MANAGE_GAME, ADMIN_SELECT_GAME, CONFIRM_DESTROY_GAME, CONFIRM_DELETE_EXPIRED = range(6)

# -------- Helpers --------
def get_active_game(user_id: int):
    return player_dal.get_active(user_id)

def get_active_game_only_if_game_active(user_id: int):
    """Get active player only if their game is still active"""
    player = player_dal.get_active(user_id)
    if player:
        game = game_dal.get_game(player["game_id"])
        if game and game.status == "active":
            return player
    return None

def get_host_id(game_id: str):
    g = db.games.find_one({"_id": ObjectId(game_id)})
    return g.get("host_id") if g else None

def exit_all_players_from_game(game_id: str):
    """Exit all players from a game when it ends"""
    try:
        # Update all players in the game to be inactive (exited from game)
        result = player_dal.col.update_many(
            {"game_id": game_id},
            {"$set": {"active": False, "game_exited": True}}
        )
        logger.info(f"Exited {result.modified_count} players from game {game_id}")
        return result.modified_count
    except Exception as e:
        logger.error(f"Error exiting players from game {game_id}: {e}")
        return 0

async def send_final_game_summaries(context, game_id: str):
    """Send each player their final game summary with debt and cash details"""
    try:
        # Get game info
        game = game_dal.get_game(game_id)
        if not game:
            return

        # Get all players who participated in the game
        all_players = player_dal.get_players(game_id)

        for player in all_players:
            try:
                # Calculate player's cash buyins
                cash_transactions = transaction_dal.col.find({
                    "game_id": game_id,
                    "user_id": player.user_id,
                    "confirmed": True,
                    "rejected": False,
                    "type": "buyin_cash"
                })
                cash_buyins = sum(tx["amount"] for tx in cash_transactions)

                # Calculate player's credit buyins (original debt)
                credit_transactions = transaction_dal.col.find({
                    "game_id": game_id,
                    "user_id": player.user_id,
                    "confirmed": True,
                    "rejected": False,
                    "type": "buyin_register"
                })
                credit_buyins = sum(tx["amount"] for tx in credit_transactions)

                # Get approved cashouts
                cashout_transactions = list(transaction_dal.col.find({
                    "game_id": game_id,
                    "user_id": player.user_id,
                    "confirmed": True,
                    "rejected": False,
                    "type": "cashout"
                }))

                total_cashed_out = sum(tx["amount"] for tx in cashout_transactions)

                # Calculate how much cash they should have received
                final_cash_received = 0
                for cashout in cashout_transactions:
                    debt_processing = cashout.get("debt_processing", {})
                    final_cash_received += debt_processing.get("final_cash_amount", 0)

                # Get current debts this player owes
                player_debts = debt_dal.get_player_debts(game_id, player.user_id)
                owes_to = []
                for debt in player_debts:
                    if debt["status"] in ["pending", "assigned"]:
                        if debt.get("creditor_user_id"):
                            # Find creditor name
                            creditor = player_dal.get_player(game_id, debt["creditor_user_id"])
                            creditor_name = creditor.name if creditor else "Unknown Player"
                            owes_to.append(f"{creditor_name}: {debt['amount']}")
                        else:
                            owes_to.append(f"Game/Bank: {debt['amount']}")

                # Get debts owed to this player
                owed_by_others = []
                # Get all debts (pending and assigned)
                all_debts = list(debt_dal.col.find({
                    "game_id": game_id,
                    "status": {"$in": ["pending", "assigned"]}
                }))
                for debt in all_debts:
                    if debt.get("creditor_user_id") == player.user_id:
                        # Find debtor name
                        debtor = player_dal.get_player(game_id, debt["debtor_user_id"])
                        debtor_name = debtor.name if debtor else "Unknown Player"
                        owed_by_others.append(f"{debtor_name}: {debt['amount']}")

                # Create final summary message
                msg = f"🏁 **Final Game Summary - {game.code}**\n\n"
                msg += f"**Your Investment:**\n"
                msg += f"• Cash buy-ins: {cash_buyins}\n"
                msg += f"• Credit buy-ins: {credit_buyins}\n"
                msg += f"• Total chips cashed out: {total_cashed_out}\n\n"

                msg += f"**Cash Settlement:**\n"
                msg += f"• Cash you received: {final_cash_received}\n\n"

                if owes_to:
                    msg += f"**💳 You owe:**\n"
                    for debt in owes_to:
                        msg += f"• {debt}\n"
                    msg += "\n"

                if owed_by_others:
                    msg += f"**💰 Others owe you:**\n"
                    for debt in owed_by_others:
                        msg += f"• {debt}\n"
                    msg += "\n"

                if not owes_to and not owed_by_others:
                    msg += f"✅ **No outstanding debts**\n\n"

                msg += f"**Summary:**\n"
                if owes_to or owed_by_others:
                    msg += f"💡 Settle outstanding debts with other players outside the game.\n"
                msg += f"🎮 Game {game.code} is now complete. Thanks for playing!"

                # Send the summary to the player
                await context.bot.send_message(
                    chat_id=player.user_id,
                    text=msg,
                    parse_mode="Markdown"
                )

            except Exception as e:
                logger.error(f"Error sending final summary to player {player.user_id}: {e}")
                continue

    except Exception as e:
        logger.error(f"Error sending final game summaries for game {game_id}: {e}")

def is_game_ended(game_id: str) -> bool:
    """Check if game is ended"""
    game = db.games.find_one({"_id": ObjectId(game_id)})
    return game and game.get("status") == "ended"

def get_host_menu(game_id: str) -> ReplyKeyboardMarkup:
    """Generate host menu dynamically based on game state"""
    # Check game status first
    game = db.games.find_one({"_id": ObjectId(game_id)})
    if game and game.get("status") == "ended":
        # Game is ended - show limited menu
        menu_rows = [
            ["📈 View Settlement", "📋 Game Report"],
            ["📊 Status", "❓ Help"]
        ]
        return ReplyKeyboardMarkup(menu_rows, resize_keyboard=True)

    # Check if all active players have cashed out
    active_player_count = db.players.count_documents({
        "game_id": game_id,
        "active": True,
        "cashed_out": False,
        "quit": False
    })

    has_active_players = active_player_count > 0

    # Build menu rows for active game
    menu_rows = [
        ["👤 Player List", "➕ Add Player"],
        ["💰 Host Buy-in", "💸 Host Cashout"],
        ["⚖️ Settle", "📈 View Settlement"],
        ["📊 Status", "📋 Game Report"],
        ["📱 Share QR", "❓ Help"]
    ]

    # Only add End Game if no active players left (all cashed out)
    if not has_active_players:
        menu_rows[0].append("🔚 End Game")

    return ReplyKeyboardMarkup(menu_rows, resize_keyboard=True)

# -------- Commands --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if this is a QR code join attempt
    if context.args and len(context.args) > 0:
        arg = context.args[0]
        if arg.startswith("join_"):
            # Extract game code from QR code parameter
            game_code = arg[5:]  # Remove "join_" prefix
            await update.message.reply_text(f"🎯 Joining game {game_code}...")

            # Set up context for join function
            context.args = [game_code]
            await join(update, context)
            return

    await update.message.reply_text(
        "🎲 **ChipBot Ready!**\n\n"
        "Commands (no / needed):\n"
        "• `newgame` - Create a new game\n"
        "• `join ABC12` - Join a game\n"
        "• `status` - Check your current game\n"
        "• `mygame` - Quick game info\n"
        "• `/admin user pass` - Admin access\n\n"
        "💡 **Tip:** Scan QR codes to join games instantly!",
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
    menu = get_host_menu(pdoc["game_id"]) if is_host else PLAYER_MENU

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
    game_id = pdoc.get("game_id")

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
            "• `🔚 End Game` - End the game permanently (appears when all players cashed out)\n"
            "• `📊 Status` - View comprehensive game status\n\n"
            "**Commands:**\n"
            "• `status` - Quick status check\n"
            "• `mygame` - Game overview",
            reply_markup=get_host_menu(game_id),
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

async def admin_system_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show system statistics and version info"""
    from src.ui.handlers.command_handlers import CHIPMATE_VERSION

    # Get system statistics
    total_games = db.games.count_documents({})
    active_games = db.games.count_documents({"status": "active"})
    total_players = db.players.count_documents({})
    active_players = db.players.count_documents({"active": True, "quit": False})
    total_transactions = db.transactions.count_documents({})
    total_debts = db.debts.count_documents({}) if hasattr(db, 'debts') else 0

    # Calculate some basic stats
    avg_players_per_game = round(total_players / max(total_games, 1), 1)
    avg_transactions_per_game = round(total_transactions / max(total_games, 1), 1)

    stats_msg = f"📈 **ChipMate System Statistics**\n\n"
    stats_msg += f"**Version:** `{CHIPMATE_VERSION}`\n\n"
    stats_msg += f"**Games:**\n"
    stats_msg += f"• Total Games: {total_games}\n"
    stats_msg += f"• Active Games: {active_games}\n"
    stats_msg += f"• Avg Players/Game: {avg_players_per_game}\n\n"
    stats_msg += f"**Players:**\n"
    stats_msg += f"• Total Players: {total_players}\n"
    stats_msg += f"• Currently Active: {active_players}\n\n"
    stats_msg += f"**Transactions:**\n"
    stats_msg += f"• Total Transactions: {total_transactions}\n"
    stats_msg += f"• Avg per Game: {avg_transactions_per_game}\n\n"
    if total_debts > 0:
        stats_msg += f"**Debts:**\n"
        stats_msg += f"• Total Debt Records: {total_debts}\n\n"
    stats_msg += f"**Database Collections:**\n"
    stats_msg += f"• Games, Players, Transactions"
    if total_debts > 0:
        stats_msg += f", Debts"

    await update.message.reply_text(
        stats_msg,
        reply_markup=ADMIN_MENU,
        parse_mode="Markdown"
    )

async def newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    host = update.effective_user

    # Check if user is already in an active game
    existing = get_active_game_only_if_game_active(host.id)
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

    # Generate QR code for easy joining
    try:
        # Get bot username from context (we'll need to pass it)
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username

        qr_image, join_url = generate_game_qr(game.code, bot_username)

        # Send game creation message with QR code
        caption = (
            f"🎮 <b>Game Created Successfully!</b>\n\n"
            f"🔑 <b>Game Code:</b> <code>{game.code}</code>\n"
            f"👑 <b>Host:</b> {host.first_name}\n\n"
            f"📱 <b>Ways to Join:</b>\n"
            f"1. Scan this QR code\n"
            f"2. Use command: <code>/join {game.code}</code>\n"
            f"3. Use link below\n\n"
            f"🎯 Share this QR code with players to join instantly!"
        )

        await update.message.reply_photo(
            photo=qr_image,
            caption=caption,
            parse_mode="HTML",
            reply_markup=get_host_menu(gid)
        )
    except Exception as e:
        # Fallback if QR generation fails
        await update.message.reply_text(
            f"🎮 Game created with code {game.code}\n"
            f"Players can join using: `/join {game.code}`",
            reply_markup=get_host_menu(gid)
        )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /join <game_code>")
        return

    user = update.effective_user

    # Check if user is already in an active game
    existing = get_active_game_only_if_game_active(user.id)
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
                await update.message.reply_text("Returning to your host menu...", reply_markup=get_host_menu(pdoc["game_id"]))
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
    # Make created_at timezone-aware if it isn't already
    created_at = game.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    if (datetime.now(timezone.utc) - created_at) > timedelta(hours=12):
        await update.message.reply_text("⚠️ This game has expired (older than 12 hours).")
        return

    gid = str(game_doc["_id"])

    # Check if user is the host trying to rejoin their own game
    if user.id == game.host_id:
        await update.message.reply_text(
            f"✅ Welcome back to your game, {user.first_name}!",
            reply_markup=get_host_menu(pdoc["game_id"])
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

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE, player_doc=None):
    user = update.effective_user

    # Use provided player_doc or get active player
    if player_doc:
        pdoc = player_doc
    else:
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
    menu = get_host_menu(pdoc["game_id"]) if is_host else PLAYER_MENU

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
    msg += f"Game Status: {'🔚 Ended' if game.status == 'ended' else '🎮 Active'}\n"
    msg += f"Cash Buy-ins: {cash_buyins}\n"
    msg += f"Credit Buy-ins: {credit_buyins}\n"
    msg += f"Player Status: {'🚪 Quit' if pdoc.get('quit') else '✅ Active'}"

    if game.status == "ended":
        msg += f"\n\n⚠️ **This game has been ended by the host.**\nNo new transactions can be processed."

    await update.message.reply_text(msg, reply_markup=menu, parse_mode="Markdown")

# -------- Buy-in conversation --------
async def buyin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user's game is ended
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    if pdoc and is_game_ended(pdoc["game_id"]):
        await update.message.reply_text(
            "🔚 **Game Has Ended**\n\n"
            "This game has been ended by the host. No new buy-ins can be processed.",
            reply_markup=ReplyKeyboardMarkup([["📊 Status"]], resize_keyboard=True)
        )
        return ConversationHandler.END

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
        chip_count = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Enter a valid number.")
        return ASK_CASHOUT

    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    gid = pdoc["game_id"]

    # Check if game is ended
    if is_game_ended(gid):
        await update.message.reply_text(
            "🔚 **Game Has Ended**\n\n"
            "This game has been ended by the host. No new transactions can be processed.\n"
            "Check with the host for final settlement.",
            reply_markup=ReplyKeyboardMarkup([["📊 Status"]], resize_keyboard=True)
        )
        return ConversationHandler.END

    # Check if this player is the host
    is_host = pdoc.get("is_host", False)

    # If host is cashing out, first they need to designate a new host
    if is_host:
        # Find other active players who can become host
        other_players = list(db.players.find({
            "game_id": gid,
            "active": True,
            "quit": False,
            "cashed_out": False,
            "user_id": {"$ne": user.id}  # Exclude current host
        }))

        if other_players:
            # Store cashout data for later use
            context.user_data["host_cashout_chip_count"] = chip_count

            # Show available players to designate as new host
            buttons = []
            for p in other_players:
                player_name = p["name"]
                buttons.append([f"{player_name}"])

            buttons.append(["❌ Cancel Cashout"])
            markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

            await update.message.reply_text(
                f"🏠 **As the host, you must designate a new host before cashing out.**\n\n"
                f"Select who will become the new host:",
                reply_markup=markup
            )
            return ASK_NEW_HOST_SELECTION

        else:
            # No other players available - host cannot cash out yet
            await update.message.reply_text(
                f"⚠️ **Cannot cash out as host**\n\n"
                f"You are the host and there are no other active players to take over hosting duties.\n"
                f"Other players must join the game first, or you can end the game instead.",
                reply_markup=get_host_menu(gid)
            )
            return ConversationHandler.END

    # Get player's own debt (they owe) and pending debts in game (others owe)
    player_debts = debt_dal.get_player_debts(gid, user.id)  # What this player owes
    pending_debts = debt_dal.get_pending_debts(gid)  # What others owe (available for transfer)

    # Calculate this player's own outstanding debt (both pending and assigned)
    player_debt_amount = sum(debt["amount"] for debt in player_debts if debt["status"] in ["pending", "assigned"])

    # Calculate available debt to transfer (only from players who have left the game)
    # Get all players to check their status
    all_players = player_dal.get_players(gid)
    inactive_player_ids = set()
    for p in all_players:
        # Include debts from players who have quit, cashed out, or are otherwise inactive
        if p.quit or (p.cashed_out and not p.active):
            inactive_player_ids.add(p.user_id)

    # Only allow debt transfer from inactive players, not from active players
    available_debt_transfer = sum(
        debt["amount"] for debt in pending_debts
        if debt["debtor_user_id"] != user.id and debt["debtor_user_id"] in inactive_player_ids
    )

    # Calculate cash buyins for this player
    transactions = transaction_dal.col.find({
        "game_id": gid,
        "user_id": user.id,
        "confirmed": True,
        "rejected": False,
        "type": "buyin_cash"
    })
    cash_buyins = sum(tx["amount"] for tx in transactions)

    # STEP 1: Calculate debt transfer from available chip count
    transfer_amount = min(chip_count, available_debt_transfer)

    # STEP 2: Final cash amount - only based on cash buy-ins, not debt settlement
    # Player keeps their debts, only gets cash for cash they put in
    final_cash = min(chip_count, cash_buyins)

    # Create summary message
    summary = f"💸 **Cashout Summary**\n\n"
    summary += f"Your chip count: {chip_count}\n"
    summary += f"Your cash buy-ins: {cash_buyins}\n"

    if player_debt_amount > 0:
        summary += f"Your outstanding debt: {player_debt_amount} (remains as debt)\n"

    if available_debt_transfer > 0:
        summary += f"\n💳 **Debt Transfer Available**\n"
        summary += f"Debts from inactive players: {available_debt_transfer}\n"
        if transfer_amount > 0:
            summary += f"Debt you'll take over: {transfer_amount}\n"

    summary += f"\n**Final Breakdown:**\n"
    summary += f"• Cash you receive: {final_cash}\n"
    if transfer_amount > 0:
        summary += f"• Debt you now collect: {transfer_amount} (others owe you)\n"

    if player_debt_amount > 0:
        summary += f"\n💳 **Your debt of {player_debt_amount} remains unchanged**"

    # Store the cashout transaction with debt info
    tx = create_cashout(gid, user.id, chip_count)
    tx_id = transaction_dal.create(tx)

    # Store debt processing information in the transaction
    debt_info = {
        "player_debt_settlement": 0,  # No debt settlement anymore
        "player_debts_to_settle": [],  # No debts are settled
        "debt_transfers": [],
        "final_cash_amount": final_cash
    }

    # Store which debts should be transferred upon approval
    if transfer_amount > 0:
        debts_to_transfer = []
        remaining_transfer = transfer_amount
        for debt in pending_debts:
            # Only transfer debts from inactive players
            if (debt["debtor_user_id"] != user.id and
                debt["debtor_user_id"] in inactive_player_ids and
                remaining_transfer > 0):
                debt_amount = min(debt["amount"], remaining_transfer)
                debts_to_transfer.append({
                    "debt_id": str(debt["_id"]),
                    "amount": debt_amount,
                    "debtor_name": debt["debtor_name"]
                })
                remaining_transfer -= debt_amount
        debt_info["debt_transfers"] = debts_to_transfer

    # Store in transaction for processing during approval
    db.transactions.update_one(
        {"_id": ObjectId(tx_id)},
        {"$set": {"debt_processing": debt_info}}
    )

    await update.message.reply_text(summary, reply_markup=PLAYER_MENU, parse_mode="Markdown")

    # Notify host with cashout and transfer details
    host_id = get_host_id(gid)
    if host_id:
        host_msg = f"📢 **Cashout Request from {user.first_name}**\n\n"
        host_msg += f"Chip count: {chip_count}\n"
        host_msg += f"Cash buy-ins: {cash_buyins}\n"

        if player_debt_amount > 0:
            host_msg += f"Player's debt: {player_debt_amount} (remains as debt)\n"

        if transfer_amount > 0:
            host_msg += f"Debt transfer: {transfer_amount}\n"

        host_msg += f"\n💵 **Cash to Pay: {final_cash}**\n"

        if transfer_amount > 0:
            host_msg += f"\n📝 **Processing:**\n"
            host_msg += f"• {user.first_name} will take over {transfer_amount} in debt from other players\n"

        buttons = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{tx_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{tx_id}")
        ]]
        await context.bot.send_message(
            chat_id=host_id,
            text=host_msg,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )
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

    if not pdoc:
        await update.message.reply_text("⚠️ You are not in an active game.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if "Yes" in text:
        db.players.update_one({"game_id": pdoc["game_id"], "user_id": user.id}, {"$set": {"quit": True, "active": False}})
        await update.message.reply_text("✅ You quit the game.", reply_markup=PLAYER_MENU)
        host_id = get_host_id(pdoc["game_id"])
        if host_id:
            await context.bot.send_message(chat_id=host_id, text=f"📢 {user.first_name} quit the game.")
    else:
        await update.message.reply_text("❌ Still in game.", reply_markup=PLAYER_MENU)
    return ConversationHandler.END

async def select_new_host(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new host selection during host cashout"""
    text = update.message.text.strip()
    user = update.effective_user

    if "Cancel Cashout" in text:
        pdoc = player_dal.get_active(user.id)
        await update.message.reply_text("Cashout cancelled.", reply_markup=get_host_menu(pdoc["game_id"]))
        return ConversationHandler.END

    # Find the selected player
    pdoc = player_dal.get_active(user.id)
    gid = pdoc["game_id"]

    selected_player = db.players.find_one({
        "game_id": gid,
        "name": text,
        "active": True,
        "quit": False,
        "cashed_out": False
    })

    if not selected_player:
        await update.message.reply_text("Invalid selection. Please choose a player from the list:")
        return ASK_NEW_HOST_SELECTION

    # Transfer host role
    new_host_id = selected_player["user_id"]

    # Remove host status from current host
    db.players.update_one(
        {"game_id": gid, "user_id": user.id},
        {"$set": {"is_host": False}}
    )

    # Set new host
    db.players.update_one(
        {"game_id": gid, "user_id": new_host_id},
        {"$set": {"is_host": True}}
    )

    # Update game host
    db.games.update_one(
        {"_id": ObjectId(gid)},
        {"$set": {"host_id": new_host_id, "host_name": selected_player["name"]}}
    )

    # Now process the original cashout
    chip_count = context.user_data["host_cashout_chip_count"]

    # Calculate cash and credit buyins from transactions
    from src.dal.transactions_dal import TransactionsDAL
    transaction_dal_temp = TransactionsDAL(db)
    transactions = transaction_dal_temp.col.find({
        "game_id": gid,
        "user_id": user.id,
        "confirmed": True,
        "rejected": False,
        "type": {"$in": ["buyin_cash", "buyin_register"]}
    })

    cash_buyins = 0
    credit_buyins = 0
    for tx in transactions:
        if tx["type"] == "buyin_cash":
            cash_buyins += tx["amount"]
        elif tx["type"] == "buyin_register":
            credit_buyins += tx["amount"]

    # Calculate cash only (no debt settlement)
    final_cash = min(chip_count, cash_buyins)

    # Create summary message
    summary = f"💸 **Cashout Summary**\n\n"
    summary += f"Host role transferred to: {selected_player['name']}\n\n"
    summary += f"Your chip count: {chip_count}\n"
    summary += f"Cash buy-ins: {cash_buyins}\n"
    summary += f"Credit buy-ins: {credit_buyins}\n\n"

    summary += f"💵 **Cash you receive: {final_cash}**\n"

    if credit_buyins > 0:
        summary += f"💳 **Your debt of {credit_buyins} remains unchanged**\n"
    else:
        summary += f"**Total cashout: {chip_count}**\n\n"
        summary += f"✅ You'll receive {chip_count} in cash."

    # Store the cashout transaction
    tx = create_cashout(gid, user.id, chip_count)
    tx_id = transaction_dal.create(tx)

    # Mark this as a former host cashout so approval doesn't deactivate them
    db.transactions.update_one(
        {"_id": ObjectId(tx_id)},
        {"$set": {"former_host_cashout": True}}
    )

    await update.message.reply_text(summary, reply_markup=PLAYER_MENU, parse_mode="Markdown")

    # Notify new host
    try:
        await context.bot.send_message(
            chat_id=new_host_id,
            text=f"🏠 **You are now the host!**\n\n"
                 f"The previous host has cashed out and designated you as the new host.\n"
                 f"You now have access to all host functions.",
            reply_markup=get_host_menu(gid)
        )
    except:
        pass  # New host might not have started bot yet

    # Notify new host about cashout approval needed
    if new_host_id:
        host_msg = f"📢 **Cashout Request from {user.first_name} (Former Host)**\n\n"
        host_msg += f"Chip count: {chip_count}\n"
        host_msg += f"Cash buy-ins: {cash_buyins}\n"
        host_msg += f"Credit debt: {credit_buyins} (remains as debt)\n\n"
        host_msg += f"💵 **Pay {user.first_name}: {final_cash} in cash**"

        buttons = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve:{tx_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject:{tx_id}")
        ]]
        await context.bot.send_message(
            chat_id=new_host_id,
            text=host_msg,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )

    return ConversationHandler.END

async def share_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and share QR code for the current game"""
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    if not pdoc or not pdoc.get("is_host"):
        await update.message.reply_text("⚠️ Only hosts can share QR codes.")
        return

    game_id = pdoc["game_id"]
    game = game_dal.get_game(game_id)
    if not game:
        await update.message.reply_text("⚠️ Game not found.")
        return

    try:
        # Get bot username
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username

        qr_image, join_url = generate_game_qr(game.code, bot_username)

        # Count current players
        players = player_dal.get_players(game_id)
        active_players = [p for p in players if p.active and not p.quit]

        caption = (
            f"📱 <b>Share this QR Code to invite players!</b>\n\n"
            f"🎮 <b>Game:</b> <code>{game.code}</code>\n"
            f"👑 <b>Host:</b> {user.first_name}\n"
            f"👥 <b>Players:</b> {len(active_players)} active\n"
            f"📅 <b>Status:</b> {game.status}\n\n"
            f"<b>How to join:</b>\n"
            f"1. 📱 Scan this QR code\n"
            f"2. 💬 Send: <code>/join {game.code}</code>\n"
            f"3. 🔗 Use link below\n\n"
            f"🎯 Forward this message to invite others!"
        )

        await update.message.reply_photo(
            photo=qr_image,
            caption=caption,
            parse_mode="HTML",
            reply_markup=get_host_menu(game_id)
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Failed to generate QR code: {str(e)}\n\n"
            f"Players can still join using: `/join {game.code}`",
            reply_markup=get_host_menu(game_id)
        )

# -------- Host menu functions --------
async def player_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of players in the game"""
    user = update.effective_user

    # Check if user is admin (either in admin mode or temporarily exited admin mode)
    is_admin = context.user_data.get("admin_auth", False) or context.user_data.get("admin_temp_exit", False)

    if is_admin and context.user_data.get("game_id"):
        # Admin access - use game_id from context
        game_id = context.user_data["game_id"]
        # Clear temp exit flag since we're handling the function now
        if context.user_data.get("admin_temp_exit"):
            context.user_data.pop("admin_temp_exit", None)
    else:
        # Regular host access
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
        # Determine player status
        if p.quit:
            status = "🚪 Quit"
        elif p.cashed_out:
            if p.active:
                status = "💰 Cashed Out (Active)"  # Former host who stayed active
            else:
                status = "💰 Cashed Out"
        elif p.active:
            status = "✅ Active"
        else:
            status = "⚠️ Inactive"

        # Calculate buyins from transactions
        transactions = db.transactions.find({
            "game_id": game_id,
            "user_id": p.user_id,
            "type": {"$in": ["buyin_cash", "buyin_register"]},
            "confirmed": True,
            "rejected": False
        })

        cash_buyins = 0
        credit_buyins = 0
        for tx in transactions:
            if tx["type"] == "buyin_cash":
                cash_buyins += tx["amount"]
            elif tx["type"] == "buyin_register":
                credit_buyins += tx["amount"]

        total_buyins = cash_buyins + credit_buyins

        # Show cashout information if player has cashed out
        cashout_info = ""
        if p.cashed_out and hasattr(p, 'final_chips') and p.final_chips is not None:
            cashout_info = f"  Final chips: {p.final_chips}\n"

        if total_buyins > 0:
            msg += f"• {p.name} ({status})\n"
            msg += f"  Cash: {cash_buyins}, Credit: {credit_buyins}\n"
            msg += f"  Total: {total_buyins}\n"
            msg += cashout_info
            msg += "\n"
        else:
            msg += f"• {p.name} ({status})\n"
            msg += f"  No buy-ins yet\n"
            msg += cashout_info
            msg += "\n"

    await update.message.reply_text(msg, reply_markup=get_host_menu(pdoc["game_id"]), parse_mode="Markdown")

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
    """Confirm ending the game - settle and close"""
    text = update.message.text
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)

    if "Yes" in text:
        game_id = pdoc["game_id"]
        players = player_dal.get_players(game_id)

        # Get active players who haven't cashed out yet
        active_players = []
        for p in players:
            if p.quit or not p.active or p.cashed_out:
                continue

            # Check if player already has a pending cashout
            existing_cashout = db.transactions.find_one({
                "game_id": game_id,
                "user_id": p.user_id,
                "type": "cashout",
                "rejected": False
            })

            if not existing_cashout:
                active_players.append(p)

        # Send cashout request to all active players
        if active_players:
            cashout_msg = (
                "🔚 **GAME ENDING NOW**\n\n"
                "The host is ending the game.\n"
                "Please submit your final chip count IMMEDIATELY.\n\n"
                "Tap 💸 Cashout to submit your chips NOW."
            )

            for p in active_players:
                try:
                    await context.bot.send_message(
                        chat_id=p.user_id,
                        text=cashout_msg,
                        reply_markup=ReplyKeyboardMarkup(
                            [["💸 Cashout"], ["📊 Status"]],
                            resize_keyboard=True
                        )
                    )
                except:
                    pass

        # Update game status to ended
        game_dal.update_status(ObjectId(game_id), "ended")

        # Exit all players from the game
        exited_count = exit_all_players_from_game(game_id)

        # Notify all other players that the game has ended and they've been exited
        all_players = player_dal.get_players(game_id)
        for p in all_players:
            if p.user_id != user.id:  # Don't notify the host again
                try:
                    if p in active_players:
                        # Already got cashout notification above
                        continue
                    else:
                        # Notify exited players
                        await context.bot.send_message(
                            chat_id=p.user_id,
                            text="🔚 **Game Has Ended**\n\n"
                                 "The host has ended the game.\n"
                                 "You have been exited from the game."
                        )
                except:
                    pass

        # Show message to host
        msg = "🔚 **Game Ended**\n\n"
        msg += f"All {exited_count} players have been exited from the game.\n\n"

        if active_players:
            msg += f"Cashout requests sent to {len(active_players)} players.\n\n"
            msg += "**Waiting for final chips from:**\n"
            for p in active_players:
                msg += f"• {p.name}\n"
            msg += "\n💡 Once all players submit, settlement will be shown.\n"
            msg += "Use '📈 View Settlement' to check status."
        else:
            msg += "All players have already cashed out.\n"
            msg += "Showing final settlement...\n"

        await update.message.reply_text(msg, reply_markup=get_host_menu(pdoc["game_id"]), parse_mode="Markdown")

        # If everyone has cashed out, show settlement immediately and send final summaries
        if not active_players:
            await show_final_settlement(update, context, game_id)
            # Send final game summaries to all players
            await send_final_game_summaries(context, game_id)
    else:
        await update.message.reply_text("❌ Game continues.", reply_markup=get_host_menu(pdoc["game_id"]))

    return ConversationHandler.END

async def settle_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate settlement - request cashout from all players"""
    user = update.effective_user

    # Check if user is admin (either in admin mode or temporarily exited admin mode)
    is_admin = context.user_data.get("admin_auth", False) or context.user_data.get("admin_temp_exit", False)

    if is_admin and context.user_data.get("game_id"):
        # Admin access - use game_id from context
        game_id = context.user_data["game_id"]
        # Clear temp exit flag since we're handling the function now
        if context.user_data.get("admin_temp_exit"):
            context.user_data.pop("admin_temp_exit", None)
    else:
        # Regular host access
        pdoc = player_dal.get_active(user.id)
        if not pdoc or not pdoc.get("is_host"):
            await update.message.reply_text("⚠️ Only hosts can settle the game.")
            return
        game_id = pdoc["game_id"]
    players = player_dal.get_players(game_id)

    # Get active players who haven't cashed out yet
    active_players = []
    for p in players:
        if p.quit or not p.active or p.cashed_out:
            continue

        # Check if player already has a pending cashout
        existing_cashout = db.transactions.find_one({
            "game_id": game_id,
            "user_id": p.user_id,
            "type": "cashout",
            "rejected": False
        })

        if not existing_cashout:
            active_players.append(p)

    if not active_players:
        # All players have cashed out or quit, show final settlement
        await show_final_settlement(update, context, game_id)
        return

    # Send cashout request to all active players
    cashout_msg = (
        "🏁 **GAME ENDING - CASHOUT REQUIRED**\n\n"
        "The host is settling the game.\n"
        "Please submit your chip count immediately.\n\n"
        "Tap 💸 Cashout to submit your final chips."
    )

    notified_count = 0
    failed_notifications = []

    for p in active_players:
        try:
            # Send urgent cashout request to each player
            await context.bot.send_message(
                chat_id=p.user_id,
                text=cashout_msg,
                reply_markup=ReplyKeyboardMarkup(
                    [["💸 Cashout"], ["📊 Status"]],
                    resize_keyboard=True
                )
            )
            notified_count += 1
        except Exception as e:
            failed_notifications.append(p.name)

    # Inform host about the settlement initiation
    host_msg = f"⚖️ **Settlement Initiated**\n\n"
    host_msg += f"Cashout requests sent to {notified_count} active players.\n\n"

    if active_players:
        host_msg += "**Waiting for cashouts from:**\n"
        for p in active_players:
            host_msg += f"• {p.name}\n"

    if failed_notifications:
        host_msg += f"\n⚠️ Failed to notify: {', '.join(failed_notifications)}\n"

    host_msg += "\n💡 Once all players submit cashouts, the final settlement will be calculated."

    await update.message.reply_text(host_msg, reply_markup=get_host_menu(pdoc["game_id"]), parse_mode="Markdown")


async def show_game_report(update: Update, context: ContextTypes.DEFAULT_TYPE, game_id, code):
    """Show comprehensive game report with all transactions"""
    game = game_dal.get_game(game_id)
    if not game:
        await update.message.reply_text("Game not found.")
        return

    # Get ALL players (including cashed out)
    all_players = player_dal.get_players(game_id)

    msg = f"📊 **GAME REPORT - {code}**\n"
    msg += f"Status: {game.status}\n"
    msg += f"Created: {game.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"

    # Process each player
    for p in all_players:
        msg += f"👤 **{p.name}**\n"

        # Player status
        if p.cashed_out:
            msg += f"Status: Cashed out at {p.cashout_time.strftime('%H:%M') if p.cashout_time else 'unknown'}\n"
        elif p.quit:
            msg += f"Status: Quit\n"
        elif p.active:
            msg += f"Status: Active\n"
        else:
            msg += f"Status: Inactive\n"

        # Get all transactions for this player
        transactions = list(db.transactions.find({
            "game_id": game_id,
            "user_id": p.user_id,
            "confirmed": True
        }).sort("at", 1))

        if transactions:
            msg += "Transactions:\n"
            cash_total = 0
            credit_total = 0
            cashout_amount = 0

            for tx in transactions:
                time_str = tx["at"].strftime("%H:%M") if "at" in tx else ""
                if tx["type"] == "buyin_cash":
                    msg += f"  • {time_str} Buy-in (Cash): +{tx['amount']}\n"
                    cash_total += tx["amount"]
                elif tx["type"] == "buyin_register":
                    msg += f"  • {time_str} Buy-in (Credit): +{tx['amount']}\n"
                    credit_total += tx["amount"]
                elif tx["type"] == "cashout":
                    msg += f"  • {time_str} Cashout: {tx['amount']} chips\n"
                    cashout_amount = tx["amount"]

            # Calculate net position
            total_buyins = cash_total + credit_total
            if cashout_amount > 0:
                net_chips = cashout_amount - total_buyins
                credit_settled = min(credit_total, cashout_amount)
                cash_received = max(0, cashout_amount - credit_total)

                msg += f"\nSummary:\n"
                msg += f"  Total buy-ins: {total_buyins} (Cash: {cash_total}, Credit: {credit_total})\n"
                msg += f"  Final chips: {cashout_amount}\n"
                msg += f"  Net: {'+' if net_chips >= 0 else ''}{net_chips}\n"

                if credit_total > 0:
                    msg += f"  Credit settled: {credit_settled}\n"
                    msg += f"  Cash received: {cash_received}\n"
            else:
                msg += f"\nTotal buy-ins: {total_buyins} (Cash: {cash_total}, Credit: {credit_total})\n"
                msg += f"No cashout yet\n"
        else:
            msg += "No transactions\n"

        msg += "\n"

    # Game totals
    all_transactions = db.transactions.find({
        "game_id": game_id,
        "confirmed": True
    })

    total_cash_buyins = 0
    total_credit_buyins = 0
    total_cashouts = 0

    for tx in all_transactions:
        if tx["type"] == "buyin_cash":
            total_cash_buyins += tx["amount"]
        elif tx["type"] == "buyin_register":
            total_credit_buyins += tx["amount"]
        elif tx["type"] == "cashout":
            total_cashouts += tx["amount"]

    msg += "**GAME TOTALS:**\n"
    msg += f"Total cash buy-ins: {total_cash_buyins}\n"
    msg += f"Total credit buy-ins: {total_credit_buyins}\n"
    msg += f"Total chips in play: {total_cash_buyins + total_credit_buyins}\n"
    msg += f"Total cashed out: {total_cashouts}\n\n"

    # Calculate settlements (who owes whom)
    msg += "**SETTLEMENTS:**\n"

    # Calculate net positions for all players who have cashed out
    player_nets = []
    for p in all_players:
        if p.cashed_out and p.final_chips is not None:
            # Get player's total buyins
            player_buyins = 0
            player_transactions = db.transactions.find({
                "game_id": game_id,
                "user_id": p.user_id,
                "type": {"$in": ["buyin_cash", "buyin_register"]},
                "confirmed": True
            })
            for tx in player_transactions:
                player_buyins += tx["amount"]

            net = p.final_chips - player_buyins
            if net != 0:  # Only include players with non-zero net
                player_nets.append({
                    "name": p.name,
                    "net": net,
                    "user_id": p.user_id
                })

    if player_nets:
        # Sort by net amount
        winners = [p for p in player_nets if p["net"] > 0]
        losers = [p for p in player_nets if p["net"] < 0]

        winners.sort(key=lambda x: x["net"], reverse=True)
        losers.sort(key=lambda x: x["net"])

        if winners and losers:
            msg += "\n💰 **Who Owes Whom:**\n"

            # Calculate who pays whom
            for loser in losers:
                debt = -loser["net"]
                msg += f"\n{loser['name']} owes {debt} total:\n"

                for winner in winners:
                    if debt <= 0:
                        break
                    if winner["net"] <= 0:
                        continue

                    payment = min(debt, winner["net"])
                    msg += f"  → Pay {winner['name']}: {payment}\n"
                    debt -= payment
                    winner["net"] -= payment

            # Reset for summary
            winners = [p for p in player_nets if p["net"] > 0]
            losers = [p for p in player_nets if p["net"] < 0]

            msg += "\n📊 **Net Results:**\n"
            for w in sorted(winners, key=lambda x: x["net"], reverse=True):
                msg += f"  • {w['name']}: +{w['net']}\n"
            for l in sorted(losers, key=lambda x: x["net"]):
                msg += f"  • {l['name']}: {l['net']}\n"
        else:
            msg += "No settlements needed yet.\n"
    else:
        msg += "No completed cashouts yet.\n"

    # Add comprehensive transaction history
    msg += "\n**📜 TRANSACTION HISTORY:**\n"

    # Get ALL transactions for the game, sorted by time
    all_game_transactions = list(db.transactions.find({
        "game_id": game_id,
        "confirmed": True
    }).sort("at", 1))

    if all_game_transactions:
        # Build a map of user_id to player name for quick lookup
        player_names = {}
        for p in all_players:
            player_names[p.user_id] = p.name

        msg += "\n"
        for tx in all_game_transactions:
            time_str = tx["at"].strftime("%H:%M") if "at" in tx else "??:??"
            player_name = player_names.get(tx["user_id"], f"Unknown (ID: {tx['user_id']})")

            if tx["type"] == "buyin_cash":
                msg += f"{time_str} - {player_name}: Buy-in (💰 Cash) +{tx['amount']}\n"
            elif tx["type"] == "buyin_register":
                msg += f"{time_str} - {player_name}: Buy-in (💳 Credit) +{tx['amount']}\n"
            elif tx["type"] == "cashout":
                msg += f"{time_str} - {player_name}: Cashout {tx['amount']} chips\n"

        # Summary statistics
        msg += "\n**Transaction Summary:**\n"
        msg += f"Total transactions: {len(all_game_transactions)}\n"

        # Count by type
        cash_buyins = sum(1 for tx in all_game_transactions if tx["type"] == "buyin_cash")
        credit_buyins = sum(1 for tx in all_game_transactions if tx["type"] == "buyin_register")
        cashouts = sum(1 for tx in all_game_transactions if tx["type"] == "cashout")

        msg += f"  • Cash buy-ins: {cash_buyins}\n"
        msg += f"  • Credit buy-ins: {credit_buyins}\n"
        msg += f"  • Cashouts: {cashouts}\n"
    else:
        msg += "No transactions recorded yet.\n"

    # Send in chunks if message is too long
    if len(msg) > 4000:
        chunks = [msg[i:i+4000] for i in range(0, len(msg), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")


async def show_final_settlement(update: Update, context: ContextTypes.DEFAULT_TYPE, game_id):
    """Show final settlement after all cashouts"""
    # Get all cashout transactions
    cashouts = db.transactions.find({
        "game_id": game_id,
        "type": "cashout",
        "confirmed": True,
        "rejected": False
    })

    # Calculate net position for each player from their cashout
    settlements = []
    for cashout in cashouts:
        player_id = cashout["user_id"]
        chip_count = cashout["amount"]

        # Get player info
        player = player_dal.get_player(game_id, player_id)
        if not player:
            continue

        # Calculate total buyins
        buyins = db.transactions.find({
            "game_id": game_id,
            "user_id": player_id,
            "type": {"$in": ["buyin_cash", "buyin_register"]},
            "confirmed": True,
            "rejected": False
        })

        cash_total = 0
        credit_total = 0
        for b in buyins:
            if b["type"] == "buyin_cash":
                cash_total += b["amount"]
            else:
                credit_total += b["amount"]

        total_buyins = cash_total + credit_total
        net = chip_count - total_buyins

        settlements.append({
            "name": player.name,
            "buyins": total_buyins,
            "cash_buyins": cash_total,
            "credit_buyins": credit_total,
            "chips": chip_count,
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

    await update.message.reply_text(msg, reply_markup=get_host_menu(game_id), parse_mode="Markdown")


async def view_settlement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View current settlement status including debt information"""
    user = update.effective_user

    # Check if user is admin (either in admin mode or temporarily exited admin mode)
    is_admin = context.user_data.get("admin_auth", False) or context.user_data.get("admin_temp_exit", False)

    if is_admin and context.user_data.get("game_id"):
        # Admin access - use game_id from context
        game_id = context.user_data["game_id"]
        # Clear temp exit flag since we're handling the function now
        if context.user_data.get("admin_temp_exit"):
            context.user_data.pop("admin_temp_exit", None)
    else:
        # Regular host access
        pdoc = player_dal.get_active(user.id)
        if not pdoc or not pdoc.get("is_host"):
            await update.message.reply_text("⚠️ Only hosts can view settlement.")
            return
        game_id = pdoc["game_id"]

    # Get ALL players (including cashed out ones for debt history)
    all_players = player_dal.get_players(game_id)

    # Get all debts in the game
    all_debts = list(debt_dal.col.find({"game_id": game_id}))

    # Organize debt information
    pending_debts = [d for d in all_debts if d["status"] == "pending"]
    assigned_debts = [d for d in all_debts if d["status"] == "assigned"]
    settled_debts = [d for d in all_debts if d["status"] == "settled"]

    msg = "📈 **Settlement & Debt Status**\n\n"

    # Show debt summary
    total_pending = sum(d["amount"] for d in pending_debts)
    total_assigned = sum(d["amount"] for d in assigned_debts)
    total_settled = sum(d["amount"] for d in settled_debts)

    if total_pending > 0 or total_assigned > 0 or total_settled > 0:
        msg += "💳 **Debt Summary:**\n"
        if total_pending > 0:
            msg += f"• Pending (unassigned): {total_pending}\n"
        if total_assigned > 0:
            msg += f"• Assigned to players: {total_assigned}\n"
        if total_settled > 0:
            msg += f"• Settled: {total_settled}\n"
        msg += f"• Total debt created: {total_pending + total_assigned + total_settled}\n\n"

    # Show current debt assignments (who owes whom)
    if assigned_debts:
        msg += "📋 **Current Debt Assignments:**\n"
        # Group by creditor
        debts_by_creditor = {}
        for debt in assigned_debts:
            creditor_id = debt["creditor_user_id"]
            if creditor_id not in debts_by_creditor:
                debts_by_creditor[creditor_id] = {
                    "creditor_name": debt["creditor_name"],
                    "debtors": []
                }
            debts_by_creditor[creditor_id]["debtors"].append({
                "name": debt["debtor_name"],
                "amount": debt["amount"]
            })

        for creditor_info in debts_by_creditor.values():
            total_owed = sum(d["amount"] for d in creditor_info["debtors"])
            msg += f"• {creditor_info['creditor_name']} is owed {total_owed}:\n"
            for debtor in creditor_info["debtors"]:
                msg += f"  - {debtor['name']}: {debtor['amount']}\n"
        msg += "\n"

    # Show settled debt history
    if settled_debts:
        msg += "✅ **Debt Settlement History:**\n"
        debt_settlements = {}
        for debt in settled_debts:
            debtor_name = debt["debtor_name"]
            if debtor_name not in debt_settlements:
                debt_settlements[debtor_name] = 0
            debt_settlements[debtor_name] += debt["amount"]

        for debtor_name, total_settled in debt_settlements.items():
            msg += f"• {debtor_name}: {total_settled} settled\n"
        msg += "\n"

    # Show cashout status
    cashed_out = []
    pending_cashouts = []
    active_no_cashout = []

    for p in all_players:
        cashout = db.transactions.find_one({
            "game_id": game_id,
            "user_id": p.user_id,
            "type": "cashout",
            "rejected": False
        })

        if cashout:
            if cashout.get("confirmed"):
                # Get debt processing info if available
                debt_processing = cashout.get("debt_processing", {})
                debt_settled = debt_processing.get("player_debt_settlement", 0)
                debt_transferred = sum(t["amount"] for t in debt_processing.get("debt_transfers", []))
                final_cash = debt_processing.get("final_cash_amount", cashout["amount"])

                cashed_out.append({
                    "name": p.name,
                    "chips": cashout["amount"],
                    "debt_settled": debt_settled,
                    "debt_transferred": debt_transferred,
                    "cash_received": final_cash,
                    "status": "Cashed out" if not p.active else "Cashed out (still active)"
                })
            else:
                pending_cashouts.append({"name": p.name, "status": "Awaiting approval"})
        elif p.active and not p.quit and not p.cashed_out:
            active_no_cashout.append({"name": p.name, "status": "No cashout yet"})

    if cashed_out:
        msg += "💰 **Completed Cashouts:**\n"
        for co in cashed_out:
            msg += f"• {co['name']}: {co['chips']} chips"
            if co['debt_settled'] > 0:
                msg += f" (settled {co['debt_settled']} debt)"
            msg += f" → {co['cash_received']} cash"
            if co['debt_transferred'] > 0:
                msg += f" + {co['debt_transferred']} debt collection\n"
            else:
                msg += f"\n"
            msg += f"  Status: {co['status']}\n"
        msg += "\n"

    if pending_cashouts:
        msg += "⏳ **Pending Cashouts:**\n"
        for p in pending_cashouts:
            msg += f"• {p['name']}: {p['status']}\n"
        msg += "\n"

    if active_no_cashout:
        msg += "🎯 **Active Players (No Cashout):**\n"
        for p in active_no_cashout:
            msg += f"• {p['name']}: {p['status']}\n"
        msg += "\n"

    if not pending_cashouts and not active_no_cashout and cashed_out:
        msg += "🎉 All players have completed cashouts!\n"
        msg += "💡 Use '📋 Game Report' for detailed final settlement.\n"
    elif active_no_cashout or pending_cashouts:
        msg += "💡 Use '⚖️ Settle' to request cashouts from remaining players."

    await update.message.reply_text(msg, reply_markup=get_host_menu(pdoc["game_id"]), parse_mode="Markdown")


# -------- Host Add Player conversation --------
async def add_player_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Host can manually add a player to the game"""
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)

    if not pdoc or not pdoc.get("is_host"):
        await update.message.reply_text("⚠️ Only hosts can add players.")
        return ConversationHandler.END

    game_id = pdoc["game_id"]
    game = game_dal.get_game(game_id)

    await update.message.reply_text(
        f"Adding player to game {game.code}\n\n"
        f"Enter the player's name:",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data["game_id"] = game_id
    context.user_data["game_code"] = game.code
    return ASK_PLAYER_NAME


async def add_player_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get the player's name and add them to the game"""
    import random

    player_name = update.message.text.strip()

    if not player_name:
        await update.message.reply_text("Please enter a valid name:")
        return ASK_PLAYER_NAME

    game_id = context.user_data["game_id"]
    game_code = context.user_data["game_code"]

    # Generate a unique negative user_id for manual players (negative to distinguish from real Telegram IDs)
    # Check existing manual players to avoid collisions
    existing_manual_ids = set()
    for p in db.players.find({"game_id": game_id, "user_id": {"$lt": 0}}):
        existing_manual_ids.add(p["user_id"])

    # Generate unique negative ID
    while True:
        user_id = -random.randint(1000, 999999)
        if user_id not in existing_manual_ids:
            break

    # Add the player
    new_player = Player(
        game_id=game_id,
        user_id=user_id,
        name=player_name,
        is_host=False
    )
    player_dal.add_player(new_player)

    # Update game's player list
    db.games.update_one(
        {"_id": ObjectId(game_id)},
        {"$addToSet": {"players": user_id}}
    )

    await update.message.reply_text(
        f"✅ Player added successfully!\n\n"
        f"Name: {player_name}\n"
        f"Game: {game_code}\n\n"
        f"This player has been added manually and can be managed through host functions.",
        reply_markup=get_host_menu(game_id)
    )
    return ConversationHandler.END


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
        game_id = context.user_data.get("game_id")
        await update.message.reply_text("Cancelled.", reply_markup=get_host_menu(game_id))
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
        game_id = context.user_data.get("game_id")
        await update.message.reply_text("Cancelled.", reply_markup=get_host_menu(game_id))
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

    # Check if this is admin override
    is_admin = context.user_data.get("admin_override", False)

    if is_admin:
        # Return to admin game management menu
        ADMIN_GAME_MENU = ReplyKeyboardMarkup(
            [
                ["👤 View Players", "💰 Add Buy-in"],
                ["💸 Add Cashout", "📊 Game Status"],
                ["⚖️ Settle Game", "🔚 End Game"],
                ["💣 Destroy Game", "🔙 Back to Games List"]
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
            reply_markup=get_host_menu(game_id)
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

    # Create keyboard with player names (exclude players who have already cashed out)
    buttons = []
    for p in players:
        if p.active and not p.quit and not p.cashed_out:
            buttons.append([f"{p.name} (ID: {p.user_id})"])

    if not buttons:
        await update.message.reply_text("No active players who haven't cashed out.")
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
        game_id = context.user_data.get("game_id")
        await update.message.reply_text("Cancelled.", reply_markup=get_host_menu(game_id))
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
        chip_count = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Enter a valid number:")
        return ASK_HOST_CASHOUT_AMOUNT

    # Get player info
    game_id = context.user_data["game_id"]
    player_id = context.user_data["target_player_id"]
    player_name = context.user_data["target_player_name"]

    # Calculate cash and credit buyins for the player
    from src.dal.transactions_dal import TransactionsDAL
    transaction_dal_temp = TransactionsDAL(db)
    transactions = transaction_dal_temp.col.find({
        "game_id": game_id,
        "user_id": player_id,
        "confirmed": True,
        "rejected": False,
        "type": {"$in": ["buyin_cash", "buyin_register"]}
    })

    cash_buyins = 0
    credit_buyins = 0
    for tx in transactions:
        if tx["type"] == "buyin_cash":
            cash_buyins += tx["amount"]
        elif tx["type"] == "buyin_register":
            credit_buyins += tx["amount"]

    # Calculate cash only (no debt settlement)
    final_cash = min(chip_count, cash_buyins)

    # Create cashout transaction
    tx = create_cashout(game_id, player_id, chip_count)
    tx_id = transaction_dal.create(tx)

    # Auto-approve since host is creating it
    transaction_dal.update_status(ObjectId(tx_id), True, False)

    # Mark the player as cashed out but keep them active in the game
    from datetime import datetime
    db.players.update_one(
        {"game_id": game_id, "user_id": player_id},
        {"$set": {
            "cashed_out": True,
            "cashout_time": datetime.now(timezone.utc),
            "active": True,  # Keep player active so they remain in game with debt
            "final_chips": chip_count
        }}
    )

    # Check if this is admin override
    is_admin = context.user_data.get("admin_override", False)

    # Create summary message
    summary = f"💸 **Cashout for {player_name}**\n\n"
    summary += f"Chip count: {chip_count}\n"
    summary += f"Cash buy-ins: {cash_buyins}\n"
    summary += f"Credit buy-ins: {credit_buyins}\n\n"

    summary += f"💵 Pay {player_name}: **{final_cash} in cash**\n"

    if credit_buyins > 0:
        summary += f"💳 {player_name}'s debt of {credit_buyins} remains unchanged.\n"
        summary += f"\n💳 {player_name} remains in the game with outstanding debt of {credit_buyins}."
    else:
        summary += f"\n✅ {player_name} has fully cashed out and may continue playing."

    if is_admin:
        # Return to admin game management menu
        ADMIN_GAME_MENU = ReplyKeyboardMarkup(
            [
                ["👤 View Players", "💰 Add Buy-in"],
                ["💸 Add Cashout", "📊 Game Status"],
                ["⚖️ Settle Game", "🔚 End Game"],
                ["💣 Destroy Game", "🔙 Back to Games List"]
            ],
            resize_keyboard=True
        )

        await update.message.reply_text(
            summary,
            reply_markup=ADMIN_GAME_MENU,
            parse_mode="Markdown"
        )

        # Notify the player with their summary
        player_msg = f"✅ Administrator recorded your cashout:\n\n"
        player_msg += f"Chips: {chip_count}\n"
        player_msg += f"Cash amount: {final_cash}\n"

        if credit_buyins > 0:
            player_msg += f"\n💳 Outstanding debt: {credit_buyins} (unchanged). You remain in the game and will need to settle this debt."
        else:
            player_msg += f"\n✅ You have fully cashed out and may continue playing!"

        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=player_msg
            )
        except:
            pass

        context.user_data["admin_override"] = False
        return ADMIN_MANAGE_GAME
    else:
        await update.message.reply_text(
            summary,
            reply_markup=get_host_menu(game_id),
            parse_mode="Markdown"
        )

        # Notify the player with their summary
        player_msg = f"✅ Host recorded your cashout:\n\n"
        player_msg += f"Chips: {chip_count}\n"
        player_msg += f"Cash amount: {final_cash}\n"

        if credit_buyins > 0:
            player_msg += f"\n💳 Outstanding debt: {credit_buyins} (unchanged). You remain in the game and will need to settle this debt."
        else:
            player_msg += f"\n✅ You have fully cashed out and may continue playing!"

        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=player_msg
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

    from src.ui.handlers.command_handlers import CHIPMATE_VERSION

    await update.message.reply_text(
        f"🔐 **Admin Mode Activated**\n\n"
        f"ChipMate Version: `{CHIPMATE_VERSION}`\n\n"
        f"Select an option from the menu:",
        reply_markup=ADMIN_MENU,
        parse_mode="Markdown"
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
            created_at = game.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - created_at) > timedelta(hours=12) and game.status == "active":
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
    """Show expired games and offer to delete them"""
    if not context.user_data.get("admin_auth"):
        await update.message.reply_text("⚠️ Admin authentication required")
        return ADMIN_MODE

    # Find all expired games (older than 12 hours)
    all_games = list(db.games.find())
    expired_games = []

    for game_doc in all_games:
        game = Game(**game_doc)
        created_at = game.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        if (datetime.now(timezone.utc) - created_at) > timedelta(hours=12):
            expired_games.append({
                "_id": game_doc["_id"],
                "code": game.code,
                "status": game.status,
                "created_at": game.created_at,
                "host_name": game.host_name
            })

    if not expired_games:
        await update.message.reply_text(
            "✅ No expired games found (older than 12 hours).",
            reply_markup=ADMIN_MENU
        )
        return ADMIN_MODE

    # Show expired games
    msg = f"⏰ **Found {len(expired_games)} Expired Games:**\n\n"

    for g in expired_games[:10]:  # Show first 10
        msg += f"• {g['code']} - {g['host_name']}\n"
        msg += f"  Created: {g['created_at'].strftime('%Y-%m-%d %H:%M')}\n"
        msg += f"  Status: {g['status']}\n\n"

    if len(expired_games) > 10:
        msg += f"... and {len(expired_games) - 10} more\n\n"

    msg += "Would you like to delete ALL expired games?"

    # Store expired game IDs for deletion
    context.user_data["expired_game_ids"] = [str(g["_id"]) for g in expired_games]

    buttons = [
        ["🗑️ Delete All Expired", "❌ Cancel"]
    ]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(msg, reply_markup=markup, parse_mode="Markdown")
    return CONFIRM_DELETE_EXPIRED

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

    # Make created_at timezone-aware if it isn't already
    created_at = game.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    # Calculate duration based on game status
    if game.status == "ended":
        # For ended games, find the last cashout time or use current time if no cashouts
        last_cashout = None
        for p in players:
            if p.cashed_out and p.cashout_time:
                cashout_time = p.cashout_time
                if cashout_time.tzinfo is None:
                    cashout_time = cashout_time.replace(tzinfo=timezone.utc)

                if last_cashout is None or cashout_time > last_cashout:
                    last_cashout = cashout_time

        if last_cashout:
            # Game duration is from creation to last cashout
            duration = last_cashout - created_at
        else:
            # If no cashouts but game ended, use current time (game just ended)
            duration = datetime.now(timezone.utc) - created_at
    else:
        # For active games, show time elapsed so far
        duration = datetime.now(timezone.utc) - created_at

    hours = int(duration.total_seconds() // 3600)
    minutes = int((duration.total_seconds() % 3600) // 60)

    if game.status == "ended":
        msg += f"Duration: {hours}h {minutes}m (ended)\n\n"
    else:
        msg += f"Duration: {hours}h {minutes}m (ongoing)\n\n"

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

            # Calculate buyins from transactions
            transactions = db.transactions.find({
                "game_id": game_id,
                "user_id": p.user_id,
                "type": {"$in": ["buyin_cash", "buyin_register"]},
                "confirmed": True,
                "rejected": False
            })

            cash_buyins = 0
            credit_buyins = 0
            for tx in transactions:
                if tx["type"] == "buyin_cash":
                    cash_buyins += tx["amount"]
                elif tx["type"] == "buyin_register":
                    credit_buyins += tx["amount"]

            total_buyins = cash_buyins + credit_buyins

            msg += f"• {p.name} (ID: {p.user_id}) {status}\n"
            if total_buyins > 0:
                msg += f"  Cash: {cash_buyins}, Credit: {credit_buyins}, Total: {total_buyins}\n\n"
            else:
                msg += f"  No buy-ins\n\n"

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
        # Show comprehensive game report like hosts get
        await show_game_report(update, context, game_id, code)
        return ADMIN_MANAGE_GAME

    elif "Settle Game" in text:
        return await admin_settle_game(update, context, game_id)

    elif "End Game" in text:
        game_dal.update_status(game_id, "ended")

        # Exit all players from the game
        exited_count = exit_all_players_from_game(game_id)

        # Notify all players
        players = player_dal.get_players(game_id)
        for p in players:
            try:
                await context.bot.send_message(
                    chat_id=p.user_id,
                    text=f"🔚 Game {code} has been ended by an administrator. You have been exited from the game."
                )
            except:
                pass

        # Send final game summaries to all players
        await send_final_game_summaries(context, game_id)

        await update.message.reply_text(f"✅ Game {code} has been ended. {exited_count} players exited. Final summaries sent to all players.")
        return ADMIN_MANAGE_GAME

    elif "Game Report" in text:
        # Generate comprehensive game report with all transactions
        await show_game_report(update, context, game_id, code)
        return ADMIN_MANAGE_GAME

    elif "Destroy Game" in text:
        # Confirm destruction
        buttons = [["✅ Yes, DESTROY", "❌ Cancel"]]
        markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

        # Count data that will be deleted
        player_count = db.players.count_documents({"game_id": game_id})
        tx_count = db.transactions.count_documents({"game_id": game_id})

        await update.message.reply_text(
            f"⚠️ **DESTRUCTIVE ACTION**\n\n"
            f"This will PERMANENTLY DELETE:\n"
            f"• Game {code}\n"
            f"• {player_count} player records\n"
            f"• {tx_count} transactions\n\n"
            f"This action CANNOT be undone!\n\n"
            f"Are you absolutely sure?",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        context.user_data["destroy_game_id"] = game_id
        context.user_data["destroy_game_code"] = code
        return CONFIRM_DESTROY_GAME

    elif "Back to Games List" in text:
        return await admin_manage_games(update, context)

    # Check if this is a host menu button while in admin game management mode
    elif text == "📋 Game Report":
        # User pressed Game Report from host menu - handle it
        await host_game_report(update, context)
        return ConversationHandler.END  # Exit admin mode
    elif text in ["👤 Player List", "⚖️ Settle", "📈 View Settlement", "📊 Status",
                   "💰 Host Buy-in", "💸 Host Cashout", "➕ Add Player", "🔚 End Game", "❓ Help"]:
        # Other host menu buttons - keep admin context and exit admin mode to handle them normally
        # Keep admin_auth and game_id in context for the host menu functions
        context.user_data["admin_temp_exit"] = True
        return ConversationHandler.END

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

async def confirm_destroy_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation of game destruction"""
    text = update.message.text

    if "Yes, DESTROY" in text:
        game_id = context.user_data.get("destroy_game_id")
        code = context.user_data.get("destroy_game_code")

        if not game_id:
            await update.message.reply_text("Error: Game ID not found.", reply_markup=ADMIN_MENU)
            return ADMIN_MODE

        # Delete all related data
        deleted_players = db.players.delete_many({"game_id": game_id})
        deleted_txs = db.transactions.delete_many({"game_id": game_id})
        deleted_game = db.games.delete_one({"_id": ObjectId(game_id)})

        msg = f"💣 **GAME DESTROYED**\n\n"
        msg += f"Game {code} has been completely deleted:\n"
        msg += f"• {deleted_players.deleted_count} player records deleted\n"
        msg += f"• {deleted_txs.deleted_count} transactions deleted\n"
        msg += f"• {deleted_game.deleted_count} game record deleted\n\n"
        msg += "All data has been permanently removed."

        await update.message.reply_text(msg, reply_markup=ADMIN_MENU, parse_mode="Markdown")
        return ADMIN_MODE
    else:
        # Cancelled
        code = context.user_data.get("destroy_game_code", "")
        await update.message.reply_text(f"❌ Destruction cancelled. Game {code} remains intact.")

        ADMIN_GAME_MENU = ReplyKeyboardMarkup(
            [
                ["👤 View Players", "💰 Add Buy-in"],
                ["💸 Add Cashout", "📊 Game Status"],
                ["⚖️ Settle Game", "🔚 End Game"],
                ["💣 Destroy Game", "🔙 Back to Games List"]
            ],
            resize_keyboard=True
        )

        return ADMIN_MANAGE_GAME


async def confirm_delete_expired(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation of deleting expired games"""
    text = update.message.text

    if "Delete All Expired" in text:
        expired_game_ids = context.user_data.get("expired_game_ids", [])

        if not expired_game_ids:
            await update.message.reply_text("No expired games to delete.", reply_markup=ADMIN_MENU)
            return ADMIN_MODE

        # Delete all expired games and their related data
        deleted_count = 0
        total_players_deleted = 0
        total_transactions_deleted = 0

        for game_id in expired_game_ids:
            # Count and delete related data
            player_count = db.players.count_documents({"game_id": game_id})
            tx_count = db.transactions.count_documents({"game_id": game_id})

            # Delete all related data
            db.players.delete_many({"game_id": game_id})
            db.transactions.delete_many({"game_id": game_id})
            result = db.games.delete_one({"_id": ObjectId(game_id)})

            if result.deleted_count > 0:
                deleted_count += 1
                total_players_deleted += player_count
                total_transactions_deleted += tx_count

        msg = f"🗑️ **Deletion Complete**\n\n"
        msg += f"Deleted {deleted_count} expired games\n"
        msg += f"Deleted {total_players_deleted} player records\n"
        msg += f"Deleted {total_transactions_deleted} transactions\n\n"
        msg += "All expired game data has been permanently removed."

        await update.message.reply_text(msg, reply_markup=ADMIN_MENU, parse_mode="Markdown")

        # Clear the stored game IDs
        context.user_data.pop("expired_game_ids", None)

    else:
        await update.message.reply_text("Deletion cancelled.", reply_markup=ADMIN_MENU)

    return ADMIN_MODE


async def admin_settle_game(update: Update, context: ContextTypes.DEFAULT_TYPE, game_id):
    """Admin settles the game"""
    players = player_dal.get_players(game_id)

    # Calculate net position for each player
    settlements = []
    for p in players:
        if p.quit or not p.active:
            continue

        # Calculate buyins from transactions
        transactions = db.transactions.find({
            "game_id": game_id,
            "user_id": p.user_id,
            "type": {"$in": ["buyin_cash", "buyin_register"]},
            "confirmed": True,
            "rejected": False
        })

        total_buyins = 0
        for tx in transactions:
            total_buyins += tx["amount"]

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

    # Check if this is a host menu button while in admin mode
    if text == "📋 Game Report":
        # User pressed Game Report from host menu - handle it
        await host_game_report(update, context)
        return ConversationHandler.END  # Exit admin mode to normal host mode
    elif text in ["👤 Player List", "⚖️ Settle", "📈 View Settlement", "📊 Status",
                   "💰 Host Buy-in", "💸 Host Cashout", "➕ Add Player", "🔚 End Game", "❓ Help"]:
        # Other host menu buttons - keep admin context and exit admin mode to handle them normally
        context.user_data["admin_temp_exit"] = True
        return ConversationHandler.END

    # Admin menu options
    if "Manage Active Games" in text:
        return await admin_manage_games(update, context)
    elif "List All Games" in text:
        return await admin_list_all_games(update, context)
    elif "Expire Old Games" in text:
        return await admin_expire_games(update, context)
    elif "📊 Game Report" in text or "Game Report" in text:
        return await admin_game_report_ask(update, context)
    elif "Find Game" in text:
        return await admin_find_game(update, context)
    elif "System Stats" in text:
        await admin_system_stats(update, context)
        return ADMIN_MODE
    elif "Help" in text:
        await admin_help(update, context)
        return ADMIN_MODE
    elif "Exit Admin" in text:
        return await admin_exit(update, context)
    else:
        await update.message.reply_text("Unknown command", reply_markup=ADMIN_MENU)
        return ADMIN_MODE

async def host_game_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive game report for host"""
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)

    if not pdoc or not pdoc.get("is_host"):
        await update.message.reply_text("⚠️ Only hosts can view game report.")
        return

    game_id = pdoc["game_id"]
    game = game_dal.get_game(game_id)
    if game:
        await show_game_report(update, context, game_id, game.code)


async def unified_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified status handler that determines if user should see player or host status"""
    user = update.effective_user

    # Check if user is admin (either in admin mode or temporarily exited admin mode)
    is_admin = context.user_data.get("admin_auth", False) or context.user_data.get("admin_temp_exit", False)

    if is_admin and context.user_data.get("game_id"):
        # Admin access - show host status for the selected game
        return await host_status(update, context)

    # Check for active player first
    pdoc = player_dal.get_active(user.id)
    if pdoc:
        # Player is active in a game
        if pdoc.get("is_host"):
            return await host_status(update, context)
        else:
            return await status(update, context, pdoc)

    # Check if player was in a game (including ended games)
    # Find most recent player record
    recent_player = db.players.find_one(
        {"user_id": user.id},
        sort=[("_id", -1)]  # Get most recent
    )

    if recent_player:
        game = game_dal.get_game(recent_player["game_id"])
        if game:
            # Show status for their most recent game
            if recent_player.get("is_host"):
                return await host_status(update, context)
            else:
                return await status(update, context, recent_player)

    # No game found
    await update.message.reply_text("⚠️ You are not in any game.")

async def host_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive game status for hosts"""
    user = update.effective_user

    # Check if user is admin (either in admin mode or temporarily exited admin mode)
    is_admin = context.user_data.get("admin_auth", False) or context.user_data.get("admin_temp_exit", False)

    if is_admin and context.user_data.get("game_id"):
        # Admin access - use game_id from context
        game_id = context.user_data["game_id"]
        # Clear temp exit flag since we're handling the function now
        if context.user_data.get("admin_temp_exit"):
            context.user_data.pop("admin_temp_exit", None)
    else:
        # Regular host access
        pdoc = player_dal.get_active(user.id)
        if not pdoc:
            # Check if user was a host in any recent game (including ended games)
            recent_player = db.players.find_one(
                {"user_id": user.id, "is_host": True},
                sort=[("_id", -1)]  # Get most recent
            )
            if recent_player:
                pdoc = recent_player
            else:
                await update.message.reply_text("⚠️ Only hosts can view status.")
                return

        if not pdoc.get("is_host"):
            await update.message.reply_text("⚠️ Only hosts can view status.")
            return

        game_id = pdoc["game_id"]

    game = game_dal.get_game(game_id)
    players = player_dal.get_players(game_id)

    # Count truly active players (not quit, and either not cashed out OR cashed out but still active like former hosts)
    active_players = sum(1 for p in players if p.active and not p.quit)

    # Calculate total buyins from transactions - only for players still in the game
    # (exclude completely cashed out players, but include former hosts who remain active)
    active_player_ids = [p.user_id for p in players if p.active and not p.quit]

    all_buyins = db.transactions.find({
        "game_id": game_id,
        "user_id": {"$in": active_player_ids},
        "type": {"$in": ["buyin_cash", "buyin_register"]},
        "confirmed": True,
        "rejected": False
    })

    total_cash = 0
    total_credit = 0
    for tx in all_buyins:
        if tx["type"] == "buyin_cash":
            total_cash += tx["amount"]
        elif tx["type"] == "buyin_register":
            total_credit += tx["amount"]

    total_buyins = total_cash + total_credit

    # Calculate total cashed out amounts
    cashouts = db.transactions.find({
        "game_id": game_id,
        "type": "cashout",
        "confirmed": True,
        "rejected": False
    })
    total_cashed_out = sum(tx["amount"] for tx in cashouts)

    # Calculate settled debt amount
    settled_debts = debt_dal.col.find({
        "game_id": game_id,
        "status": "settled"
    })
    total_debt_settled = sum(debt["amount"] for debt in settled_debts)

    msg = f"📊 **Game Status**\n\n"
    msg += f"Code: **{game.code}**\n"
    msg += f"Status: {game.status}\n"
    msg += f"Players: {active_players} active\n\n"
    msg += f"💰 **Money Currently in Play:**\n"
    msg += f"• Cash buy-ins: {total_cash}\n"
    msg += f"• Credit buy-ins: {total_credit}\n"
    msg += f"• Total in play: {total_buyins}\n\n"
    if total_cashed_out > 0 or total_debt_settled > 0:
        msg += f"📤 **Already Settled:**\n"
        if total_cashed_out > 0:
            msg += f"• Cashed out: {total_cashed_out} chips\n"
        if total_debt_settled > 0:
            msg += f"• Debt settled: {total_debt_settled}\n"

    await update.message.reply_text(msg, reply_markup=get_host_menu(game_id), parse_mode="Markdown")

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
        # Use transaction service to handle approval (includes debt creation)
        from src.bl.transaction_service import TransactionService
        transaction_service = TransactionService(MONGO_URL)
        transaction_service.approve_transaction(tx_id)

        # If this is a cashout, process debt settlement and transfers
        if tx["type"] == "cashout":
            game_id = tx["game_id"]
            user_id = tx["user_id"]
            chip_count = tx["amount"]

            # Get player info
            player = player_dal.get_player(game_id, user_id)
            player_name = player.name if player else "Player"
            was_host = player.is_host if player else False
            is_former_host_cashout = tx.get("former_host_cashout", False)

            # Get debt processing information
            debt_processing = tx.get("debt_processing", {})
            debt_transfers = debt_processing.get("debt_transfers", [])
            final_cash = debt_processing.get("final_cash_amount", chip_count)

            # STEP 1: Process debt transfers (no debt settlement anymore)
            total_debt_transferred = 0
            transfer_notifications = []

            for transfer in debt_transfers:
                debt_id = transfer["debt_id"]
                transfer_amount = transfer["amount"]
                debtor_name = transfer["debtor_name"]

                # Assign the debt to the cashing out player
                success = debt_dal.assign_debt_to_creditor(debt_id, user_id, player_name)
                if success:
                    total_debt_transferred += transfer_amount
                    transfer_notifications.append({
                        "debtor_name": debtor_name,
                        "amount": transfer_amount,
                        "debt_id": debt_id
                    })

            # Mark player as cashed out
            from datetime import datetime
            if is_former_host_cashout or was_host:
                # Former host or current host stays active in the game as regular player
                db.players.update_one(
                    {"game_id": game_id, "user_id": user_id},
                    {"$set": {
                        "cashed_out": True,
                        "cashout_time": datetime.now(timezone.utc),
                        "active": True,  # Keep active as regular player
                        "is_host": False,  # Ensure not host anymore
                        "final_chips": chip_count
                    }}
                )
            else:
                # Regular player - keep active in game with debt if applicable
                db.players.update_one(
                    {"game_id": game_id, "user_id": user_id},
                    {"$set": {
                        "cashed_out": True,
                        "cashout_time": datetime.now(timezone.utc),
                        "active": True,  # Keep active so they remain in game with debt
                        "final_chips": chip_count
                    }}
                )

            # Handle host succession - hosts now stay in game but need new host assigned
            new_host_assigned = False
            if was_host:
                # Auto-assign new host if needed
                remaining_players = player_dal.get_players(game_id)
                active_remaining = [p for p in remaining_players if p.active and not p.quit and not p.cashed_out]

                if active_remaining:
                    new_host = active_remaining[0]
                    db.players.update_one(
                        {"game_id": game_id, "user_id": new_host.user_id},
                        {"$set": {"is_host": True}}
                    )
                    db.games.update_one(
                        {"_id": ObjectId(game_id)},
                        {"$set": {"host_id": new_host.user_id, "host_name": new_host.name}}
                    )
                    new_host_assigned = True

                    try:
                        await context.bot.send_message(
                            chat_id=new_host.user_id,
                            text=f"🎩 You are now the host of the game!",
                            reply_markup=get_host_menu(game_id)
                        )
                    except:
                        pass

            # Create approval message
            cashout_msg = f"✅ Approved cashout: {chip_count} chips\n"
            cashout_msg += f"💵 Cash paid: {final_cash}\n"

            if total_debt_transferred > 0:
                cashout_msg += f"💳 Debt transferred to player: {total_debt_transferred}\n\n"
                cashout_msg += f"Debts transferred to {player_name}:\n"
                for notif in transfer_notifications:
                    cashout_msg += f"• {notif['debtor_name']}: {notif['amount']}\n"
            else:
                cashout_msg += f"💵 Cash to pay: {final_cash}\n"

            if is_former_host_cashout or was_host:
                cashout_msg += f"\n👤 {player_name} (host/former host) remains in the game as a regular player."
            else:
                cashout_msg += f"\n🚪 {player_name} has been removed from the game."

            if was_host and new_host_assigned:
                cashout_msg += f"\n🎩 New host assigned automatically."

            await query.edit_message_text(cashout_msg)

            # Notify the cashing out player
            player_notification = f"✅ Cashout approved: {chip_count} chips\n"
            player_notification += f"💵 Cash you receive: {final_cash}\n"

            if total_debt_transferred > 0:
                debt_transfer_msg = message_formatter.format_debt_transfer_notification(
                    transfer_notifications, total_debt_transferred
                )
                player_notification += f"\n{debt_transfer_msg}\n"

            if is_former_host_cashout or was_host:
                player_notification += "\n👤 You remain in the game as a regular player."
            else:
                # Check if player has debt - get their current debt amount (both pending and assigned)
                current_debts = debt_dal.get_player_debts(game_id, user_id)
                current_debt = sum(debt["amount"] for debt in current_debts if debt["status"] in ["pending", "assigned"])
                if current_debt > 0:
                    player_notification += f"\n💳 Outstanding debt: {current_debt}. You remain in the game and will need to settle this debt."
                else:
                    player_notification += "\n✅ You have fully cashed out and may continue playing!"

            await context.bot.send_message(chat_id=user_id, text=player_notification)

            # Notify debtors about the transfer - consolidate by debtor
            debtor_notifications = {}
            for notif in transfer_notifications:
                debtor_debt = db.debts.find_one({"_id": ObjectId(notif['debt_id'])})
                if debtor_debt:
                    debtor_id = debtor_debt['debtor_user_id']
                    if debtor_id not in debtor_notifications:
                        debtor_notifications[debtor_id] = {
                            "total_amount": 0,
                            "creditor_name": player_name
                        }
                    debtor_notifications[debtor_id]["total_amount"] += notif['amount']

            # Send consolidated notifications
            for debtor_id, info in debtor_notifications.items():
                try:
                    await context.bot.send_message(
                        chat_id=debtor_id,
                        text=f"💳 **Debt Transfer Notice**\n\n"
                             f"Your total debt of {info['total_amount']} has been transferred to {info['creditor_name']}.\n"
                             f"You now owe {info['creditor_name']} this amount instead of the game.",
                        parse_mode="Markdown"
                    )
                except:
                    pass  # Player might not have started bot
        else:
            # Regular buy-in approval
            await query.edit_message_text(f"✅ Approved {tx['type']} {tx['amount']}")

            # Send notification to player with debt info if register buyin
            if tx['type'] == 'buyin_register':
                player_msg = (
                    f"✅ Approved {tx['type']} {tx['amount']}\n\n"
                    f"💳 You now owe {tx['amount']} to the game.\n"
                    f"This debt will be transferred to other players when they cash out."
                )
                await context.bot.send_message(chat_id=tx["user_id"], text=player_msg)
            else:
                await context.bot.send_message(chat_id=tx["user_id"], text=f"✅ Approved {tx['type']} {tx['amount']}")

            # Note: Debt creation for register buyin is now handled by TransactionService
            # No need to create debt record here - it's handled in the service layer
    else:
        # Handle rejection with suggestions
        transaction_dal.update_status(ObjectId(tx_id), False, True)
        if tx["type"] == "cashout":
            await query.edit_message_text(f"❌ Rejected cashout: {tx['amount']} chips\n💡 Alternative suggestions sent to player")
        else:
            await query.edit_message_text(f"❌ Rejected {tx['type']} {tx['amount']}")

        # Provide helpful suggestions for rejected cashouts
        if tx["type"] == "cashout":
            game_id = tx["game_id"]
            user_id = tx["user_id"]
            chip_count = tx["amount"]

            # Get player info and debt processing details
            player = player_dal.get_player(game_id, user_id)
            player_name = player.name if player else "Player"

            # Check if this cashout had debt processing information
            debt_processing = tx.get("debt_processing", {})
            player_debt = debt_processing.get("player_debt_settlement", 0)
            debt_transfers = debt_processing.get("debt_transfers", [])
            final_cash = debt_processing.get("final_cash_amount", chip_count)

            # Generate suggestions based on the cashout details
            suggestion_msg = f"❌ **Cashout Rejected: {chip_count} chips**\n\n"
            suggestion_msg += "💡 **Consider these alternatives:**\n\n"

            suggestions = []

            # Suggest different chip amount if current amount seems problematic
            if chip_count > 200:
                suggestions.append(f"🔢 Try a smaller amount (e.g., {chip_count // 2} chips)")

            # If player has debt, suggest settling more debt first
            if player_debt > 0:
                suggestions.append(f"💳 Consider playing longer to settle your {player_debt} debt")

            # If there were debt transfers available, explain the benefit
            if debt_transfers:
                total_transfer = sum(d["amount"] for d in debt_transfers)
                suggestions.append(f"📈 With debt transfer, you'd get {final_cash} cash instead of {chip_count}")

            # Check player's transaction history for better suggestions
            player_transactions = list(db.transactions.find({
                "game_id": game_id,
                "user_id": user_id,
                "confirmed": True,
                "type": {"$in": ["buyin_cash", "buyin_register"]}
            }))

            total_buyins = sum(tx["amount"] for tx in player_transactions)
            if total_buyins > 0:
                # Suggest waiting if cashout is much less than buyins
                if chip_count < total_buyins * 0.8:
                    suggestions.append(f"🎯 Your buyins total {total_buyins} - consider playing longer")
                # Suggest different timing
                suggestions.append("⏰ Try cashing out at a different time")

            # General suggestions
            suggestions.append("🗣️ Talk to the host about the best cashout amount")
            suggestions.append("♻️ You can request a new cashout anytime")

            # Add suggestions to message
            for i, suggestion in enumerate(suggestions[:4], 1):  # Limit to 4 suggestions
                suggestion_msg += f"{i}. {suggestion}\n"

            suggestion_msg += f"\n💬 **Reason**: The host felt this wasn't the right time/amount."
            suggestion_msg += f"\n\n🔄 You can make a new cashout request anytime using 💸 Cashout."

            await context.bot.send_message(
                chat_id=user_id,
                text=suggestion_msg,
                parse_mode="Markdown"
            )
        else:
            # Regular rejection for non-cashout transactions
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

    # Host menu handlers - MUST come before admin conversation handler
    app.add_handler(MessageHandler(filters.Regex("^👤 Player List$"), player_list))
    app.add_handler(MessageHandler(filters.Regex("^⚖️ Settle$"), settle_game))
    app.add_handler(MessageHandler(filters.Regex("^📈 View Settlement$"), view_settlement))
    app.add_handler(MessageHandler(filters.Regex("^📊 Status$"), unified_status))
    app.add_handler(MessageHandler(filters.Regex("^📋 Game Report$"), host_game_report))
    app.add_handler(MessageHandler(filters.Regex("^📱 Share QR$"), share_qr))

    # Player/Host conversation handlers
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Buy-in$"), buyin_start)],
        states={ASK_BUYIN_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, buyin_type)],
                ASK_BUYIN_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, buyin_amount)]},
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💸 Cashout$"), cashout_start)],
        states={
            ASK_CASHOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cashout_amount)],
            ASK_NEW_HOST_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_new_host)]
        },
        fallbacks=[]
    ))
    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🚪 Quit$"), quit_start)],
        states={ASK_QUIT_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, quit_confirm)]},
        fallbacks=[]
    ))

    # Admin conversation handler - MUST come after host menu handlers
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin_login),
            MessageHandler(filters.Regex(r"(?i)^admin\s+\w+\s+\w+$"), admin_text_login)
        ],
        states={
            ADMIN_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_mode_handler)],
            ASK_GAME_CODE_REPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_game_report)],
            ADMIN_SELECT_GAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_select_game)],
            ADMIN_MANAGE_GAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_manage_game_handler)],
            CONFIRM_DESTROY_GAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_destroy_game)],
            CONFIRM_DELETE_EXPIRED: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete_expired)]
        },
        fallbacks=[MessageHandler(filters.Regex("^🚪 Exit Admin$"), admin_exit)]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔚 End Game$"), end_game_start)],
        states={ASK_END_GAME_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, end_game_confirm)]},
        fallbacks=[]
    ))

    app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Add Player$"), add_player_start)],
        states={
            ASK_PLAYER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_player_name)]
        },
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
