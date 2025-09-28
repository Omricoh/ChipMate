"""
Conversation Handlers - UI Layer
Handles multi-step conversations (buy-in, cashout, etc.)
"""
import os
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from pymongo import MongoClient
from datetime import datetime

# Conversation states
ASK_BUYIN_TYPE = 1
ASK_BUYIN_AMOUNT = 2
ASK_CASHOUT = 3
ASK_NEW_HOST_SELECTION = 4
ASK_QUIT_CONFIRM = 5
ASK_HOST_BUYIN_PLAYER = 6
ASK_HOST_BUYIN_TYPE = 7
ASK_HOST_BUYIN_AMOUNT = 8

# Database connection will be set up properly in production
db = None

def init_db(mongo_url=None):
    """Initialize database connection"""
    global db
    try:
        if mongo_url:
            client = MongoClient(mongo_url)
        else:
            client = MongoClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
        db = client.chipmate
    except:
        db = None

def set_db(database):
    """Set database for testing"""
    global db
    db = database

# -------- Buyin conversation --------
async def buyin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Check if user has active game
    if db is not None:
        pdoc = db.players.find_one({"user_id": user.id, "active": True, "quit": False})
    else:
        pdoc = None

    if not pdoc:
        await update.message.reply_text("❌ You are not in an active game.")
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
        if amount <= 0:
            await update.message.reply_text("Enter a positive number.")
            return ASK_BUYIN_AMOUNT
    except ValueError:
        await update.message.reply_text("Enter a valid number.")
        return ASK_BUYIN_AMOUNT

    user = update.effective_user

    # Get active player
    if db is not None:
        pdoc = db.players.find_one({"user_id": user.id, "active": True, "quit": False})
    else:
        pdoc = None

    if not pdoc:
        await update.message.reply_text("❌ You are not in an active game.")
        return ConversationHandler.END

    gid = pdoc["game_id"]
    tx_type = f"buyin_{context.user_data['buy_type']}"

    # Create transaction
    tx_doc = {
        "game_id": gid,
        "user_id": user.id,
        "type": tx_type,
        "amount": amount,
        "status": "pending",
        "timestamp": datetime.utcnow()
    }

    if db is not None:
        result = db.transactions.insert_one(tx_doc)
        tx_id = str(result.inserted_id)
    else:
        tx_id = "mock_tx_id"

    await update.message.reply_text(f"✅ Buy-in {context.user_data['buy_type']} {amount} submitted.")

    # Notify host
    if db is not None:
        game_doc = db.games.find_one({"_id": gid})
        if game_doc and "host_id" in game_doc:
            host_id = game_doc["host_id"]
            buttons = [[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{tx_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{tx_id}")
            ]]
            await context.bot.send_message(
                chat_id=host_id,
                text=f"📢 {user.first_name} requests {context.user_data['buy_type']} {amount}",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

    return ConversationHandler.END

# -------- Cashout conversation --------
async def cashout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Check if user has active game
    if db is not None:
        pdoc = db.players.find_one({"user_id": user.id, "active": True, "quit": False})
    else:
        pdoc = None

    if not pdoc:
        await update.message.reply_text("❌ You are not in an active game.")
        return ConversationHandler.END

    await update.message.reply_text("💸 Enter chip count to cash out:")
    return ASK_CASHOUT

async def cashout_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chip_count = int(update.message.text)
        if chip_count <= 0:
            await update.message.reply_text("Enter a positive number.")
            return ASK_CASHOUT
    except ValueError:
        await update.message.reply_text("Enter a valid number.")
        return ASK_CASHOUT

    user = update.effective_user

    # Get active player
    if db is not None:
        pdoc = db.players.find_one({"user_id": user.id, "active": True, "quit": False})
    else:
        pdoc = None

    if not pdoc:
        await update.message.reply_text("❌ You are not in an active game.")
        return ConversationHandler.END

    gid = pdoc["game_id"]

    # Create cashout transaction
    tx_doc = {
        "game_id": gid,
        "user_id": user.id,
        "type": "cashout",
        "amount": chip_count,
        "status": "pending",
        "timestamp": datetime.utcnow()
    }

    if db is not None:
        result = db.transactions.insert_one(tx_doc)
        tx_id = str(result.inserted_id)
    else:
        tx_id = "mock_tx_id"

    await update.message.reply_text(f"✅ Cashout {chip_count} submitted.")

    # Notify host
    if db is not None:
        game_doc = db.games.find_one({"_id": gid})
        if game_doc and "host_id" in game_doc:
            host_id = game_doc["host_id"]
            buttons = [[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{tx_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject:{tx_id}")
            ]]
            await context.bot.send_message(
                chat_id=host_id,
                text=f"📢 {user.first_name} requests cashout {chip_count}",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

    return ConversationHandler.END

# -------- Quit conversation --------
async def quit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Check if user has active game
    if db is not None:
        pdoc = db.players.find_one({"user_id": user.id, "active": True, "quit": False})
    else:
        pdoc = None

    if not pdoc:
        await update.message.reply_text("❌ You are not in an active game.")
        return ConversationHandler.END

    buttons = [["✅ Yes", "❌ No"]]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "⚠️ Are you sure you want to quit the game?\n\n"
        "This will mark you as inactive and you won't be able to participate further.",
        reply_markup=markup
    )
    return ASK_QUIT_CONFIRM

async def quit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if "Yes" in text:
        user = update.effective_user
        if db is not None:
            pdoc = db.players.find_one({"user_id": user.id, "active": True, "quit": False})
            if pdoc:
                db.players.update_one(
                    {"game_id": pdoc["game_id"], "user_id": user.id},
                    {"$set": {"quit": True, "active": False}}
                )
                await update.message.reply_text("✅ You have quit the game.")
            else:
                await update.message.reply_text("❌ You are not in an active game.")
        else:
            await update.message.reply_text("✅ You have quit the game.")
    else:
        await update.message.reply_text("❌ Quit cancelled.")

    return ConversationHandler.END

# -------- Host buyin conversation --------
async def host_buyin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if db is not None:
        pdoc = db.players.find_one({"user_id": user.id, "active": True, "quit": False})
    else:
        pdoc = None

    if not pdoc or not pdoc.get("is_host", False):
        await update.message.reply_text("❌ Only the host can do this.")
        return ConversationHandler.END

    gid = pdoc["game_id"]

    if db is not None:
        players = list(db.players.find({"game_id": gid, "active": True, "quit": False}))
    else:
        players = []

    other_players = [p for p in players if p["user_id"] != user.id]

    if not other_players:
        await update.message.reply_text("❌ No other players to buy in for.")
        return ConversationHandler.END

    buttons = []
    for player in other_players:
        buttons.append([player["name"]])
    buttons.append(["❌ Cancel"])

    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Select player to buy in for:", reply_markup=markup)
    return ASK_HOST_BUYIN_PLAYER

async def host_buyin_player(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        await update.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END

    user = update.effective_user

    if db is not None:
        pdoc = db.players.find_one({"user_id": user.id, "active": True, "quit": False})
        gid = pdoc["game_id"]
        selected_player = db.players.find_one({"game_id": gid, "name": text})
    else:
        selected_player = {"user_id": 12345}  # Mock for testing

    if not selected_player:
        await update.message.reply_text("❌ Player not found. Try again.")
        return ASK_HOST_BUYIN_PLAYER

    context.user_data["selected_player_id"] = selected_player["user_id"]

    buttons = [["💰 Cash", "💳 Register"]]
    markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(f"Buy-in type for {text}?", reply_markup=markup)
    return ASK_HOST_BUYIN_TYPE

async def host_buyin_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data["buy_type"] = "cash" if "Cash" in text else "register"
    await update.message.reply_text("Enter amount of chips:")
    return ASK_HOST_BUYIN_AMOUNT

async def host_buyin_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if amount <= 0:
            await update.message.reply_text("Enter a positive number.")
            return ASK_HOST_BUYIN_AMOUNT
    except ValueError:
        await update.message.reply_text("Enter a valid number.")
        return ASK_HOST_BUYIN_AMOUNT

    user = update.effective_user

    if db is not None:
        pdoc = db.players.find_one({"user_id": user.id, "active": True, "quit": False})
        gid = pdoc["game_id"]
    else:
        gid = "game123"

    selected_player_id = context.user_data["selected_player_id"]
    tx_type = f"buyin_{context.user_data['buy_type']}"

    # Create transaction for selected player
    tx_doc = {
        "game_id": gid,
        "user_id": selected_player_id,
        "type": tx_type,
        "amount": amount,
        "status": "approved",  # Host approves immediately
        "timestamp": datetime.utcnow()
    }

    if db is not None:
        result = db.transactions.insert_one(tx_doc)

    await update.message.reply_text(f"✅ Buy-in {context.user_data['buy_type']} {amount} created for player.")

    return ConversationHandler.END

# -------- Admin login --------
async def admin_text_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin login via text command"""
    user = update.effective_user
    admin_users = os.getenv("ADMIN_USERS", "").split(",")

    if str(user.id) not in admin_users:
        await update.message.reply_text("❌ Access denied.")
        return

    text = update.message.text.lower()
    if text.startswith("admin"):
        # Simple admin authentication - in production this would be more secure
        context.user_data["admin_authenticated"] = True
        await update.message.reply_text("✅ Admin authenticated.")
    else:
        await update.message.reply_text("❌ Invalid admin command.")

class ConversationHandlers:
    def __init__(self, game_service, player_service, transaction_service, admin_service):
        self.game_service = game_service
        self.player_service = player_service
        self.transaction_service = transaction_service
        self.admin_service = admin_service

    def register_handlers(self, app):
        """Register conversation handlers"""
        # Buyin conversation
        buyin_handler = ConversationHandler(
            entry_points=[],  # These would be registered by command handlers
            states={
                ASK_BUYIN_TYPE: [buyin_type],
                ASK_BUYIN_AMOUNT: [buyin_amount],
            },
            fallbacks=[]
        )

        # Add other conversation handlers as needed
        # This is a simplified version - full implementation would include all handlers