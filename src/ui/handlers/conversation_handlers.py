"""
Conversation Handlers - UI Layer
Handles multi-step conversations (buy-in, cashout, etc.)
"""
import os
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from src.dal.players_dal import PlayerDAL
from src.dal.transactions_dal import TransactionDAL
from src.dal.games_dal import GameDAL
from src.dal.debt_dal import DebtDAL
from src.models.transaction import Transaction
from src.ui.menus.menu_builder import MenuBuilder
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

# Initialize DALs - these will be replaced with dependency injection in production
player_dal = PlayerDAL()
transaction_dal = TransactionDAL()
game_dal = GameDAL()
debt_dal = DebtDAL()
menu_builder = MenuBuilder()

# -------- Buyin conversation --------
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
        if amount <= 0:
            await update.message.reply_text("Enter a positive number.")
            return ASK_BUYIN_AMOUNT
    except ValueError:
        await update.message.reply_text("Enter a valid number.")
        return ASK_BUYIN_AMOUNT

    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    if not pdoc:
        await update.message.reply_text("❌ You are not in an active game.")
        return ConversationHandler.END

    gid = pdoc["game_id"]
    tx_type = f"buyin_{context.user_data['buy_type']}"

    # Create transaction
    tx = Transaction(
        game_id=gid,
        user_id=user.id,
        type=tx_type,
        amount=amount,
        status="pending",
        timestamp=datetime.utcnow()
    )

    tx_id = transaction_dal.create(tx)
    await update.message.reply_text(f"✅ Buy-in {context.user_data['buy_type']} {amount} submitted.", reply_markup=menu_builder.get_player_menu())

    # Notify host
    game_doc = game_dal.get_by_id(gid)
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
    pdoc = player_dal.get_active(user.id)
    if not pdoc:
        await update.message.reply_text("❌ You are not in an active game.")
        return ConversationHandler.END

    gid = pdoc["game_id"]
    is_host = pdoc.get("is_host", False)

    # Create cashout transaction
    tx = Transaction(
        game_id=gid,
        user_id=user.id,
        type="cashout",
        amount=chip_count,
        status="pending",
        timestamp=datetime.utcnow()
    )

    tx_id = transaction_dal.create(tx)
    await update.message.reply_text(f"✅ Cashout {chip_count} submitted.", reply_markup=menu_builder.get_player_menu())

    # Notify host
    game_doc = game_dal.get_by_id(gid)
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
        pdoc = player_dal.get_active(user.id)
        if pdoc:
            player_dal.update_player(pdoc["game_id"], user.id, {"quit": True, "active": False})
            await update.message.reply_text("✅ You have quit the game.", reply_markup=menu_builder.get_main_menu())
        else:
            await update.message.reply_text("❌ You are not in an active game.", reply_markup=menu_builder.get_main_menu())
    else:
        await update.message.reply_text("❌ Quit cancelled.", reply_markup=menu_builder.get_player_menu())

    return ConversationHandler.END

# -------- Host buyin conversation --------
async def host_buyin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    if not pdoc or not pdoc.get("is_host", False):
        await update.message.reply_text("❌ Only the host can do this.")
        return ConversationHandler.END

    gid = pdoc["game_id"]
    players = list(player_dal.get_active_players(gid))
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
        await update.message.reply_text("❌ Cancelled.", reply_markup=menu_builder.get_host_menu(context.user_data.get("game_id")))
        return ConversationHandler.END

    user = update.effective_user
    pdoc = player_dal.get_active(user.id)
    gid = pdoc["game_id"]

    # Find player by name
    selected_player = player_dal.get_player_by_name(gid, text)
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
    pdoc = player_dal.get_active(user.id)
    gid = pdoc["game_id"]
    selected_player_id = context.user_data["selected_player_id"]
    tx_type = f"buyin_{context.user_data['buy_type']}"

    # Create transaction for selected player
    tx = Transaction(
        game_id=gid,
        user_id=selected_player_id,
        type=tx_type,
        amount=amount,
        status="approved",  # Host approves immediately
        timestamp=datetime.utcnow()
    )

    tx_id = transaction_dal.create(tx)
    await update.message.reply_text(
        f"✅ Buy-in {context.user_data['buy_type']} {amount} created for player.",
        reply_markup=menu_builder.get_host_menu(gid)
    )

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
        await update.message.reply_text("✅ Admin authenticated.", reply_markup=menu_builder.get_admin_menu())
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