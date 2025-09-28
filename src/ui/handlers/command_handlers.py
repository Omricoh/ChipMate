"""
Command Handlers - UI Layer
Handles basic bot commands and routing
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from src.ui.menus.menu_builder import MenuBuilder
from src.ui.formatters.message_formatter import MessageFormatter

logger = logging.getLogger("chipbot")

class CommandHandlers:
    """Handles basic bot commands"""

    def __init__(self, game_service, player_service, transaction_service, admin_service):
        self.game_service = game_service
        self.player_service = player_service
        self.transaction_service = transaction_service
        self.admin_service = admin_service

        self.formatter = MessageFormatter()

    def register_handlers(self, app):
        """Register all command handlers"""
        # Basic commands
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(MessageHandler(filters.Regex(r"(?i)^start$"), self.start))

        app.add_handler(CommandHandler("newgame", self.newgame))
        app.add_handler(MessageHandler(filters.Regex(r"(?i)^newgame$"), self.newgame))

        app.add_handler(CommandHandler("join", self.join))
        app.add_handler(CommandHandler("status", self.status))
        app.add_handler(CommandHandler("mygame", self.mygame))
        app.add_handler(CommandHandler("help", self.help_handler))

        # Menu button handlers
        app.add_handler(MessageHandler(filters.Regex(r"(?i)^help$"), self.help_handler))
        app.add_handler(MessageHandler(filters.Regex("^❓ Help$"), self.help_handler))
        app.add_handler(MessageHandler(filters.Regex("^📊 Status$"), self.status))

        # Host menu handlers
        app.add_handler(MessageHandler(filters.Regex("^👤 Player List$"), self.player_list))
        app.add_handler(MessageHandler(filters.Regex("^📊 Status$"), self.host_status))
        app.add_handler(MessageHandler(filters.Regex("^📱 Share QR$"), self.share_qr))

        # Admin commands
        app.add_handler(CommandHandler("admin", self.admin_login))
        app.add_handler(MessageHandler(filters.Regex(r"(?i)^admin\s+\w+\s+\w+$"), self.admin_text_login))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command and auto-join functionality"""
        user = update.effective_user

        # Check for auto-join parameter
        if context.args and len(context.args) > 0:
            arg = context.args[0]
            if arg.startswith("join_"):
                game_code = arg[5:]  # Remove "join_" prefix
                return await self._auto_join_game(update, context, game_code)

        # Check if user is already in an active game
        active_player = self.player_service.get_active_player(user.id)
        if active_player:
            game = self.game_service.get_game(active_player["game_id"])
            if game:
                menu = MenuBuilder.get_host_menu() if active_player.get("is_host") else MenuBuilder.get_player_menu()
                await update.message.reply_text(
                    f"Welcome back! You're in game **{game.code}**",
                    reply_markup=menu,
                    parse_mode="Markdown"
                )
                return

        # Welcome new user
        welcome_msg = (
            "🎮 **Welcome to ChipMate!**\n\n"
            "Your poker game companion for tracking chips and settlements.\n\n"
            "**Getting Started:**\n"
            "• `/newgame` - Create a new game\n"
            "• `/join CODE` - Join existing game\n"
            "• `/help` - Get help\n\n"
            "Ready to play? 🃏"
        )

        await update.message.reply_text(welcome_msg, parse_mode="Markdown")

    async def _auto_join_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE, game_code: str):
        """Handle auto-join from QR code or link"""
        user = update.effective_user

        try:
            game_id = self.game_service.join_game(game_code, user.id, user.first_name)
            if game_id:
                game = self.game_service.get_game(game_id)
                await update.message.reply_text(
                    f"🎉 Successfully joined game **{game.code}**!\n\n"
                    f"Host: {game.host_name}\n"
                    f"You can now buy-in and play!",
                    reply_markup=MenuBuilder.get_player_menu(),
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ Could not join game '{game_code}'. "
                    f"Game might not exist or be expired."
                )
        except Exception as e:
            logger.error(f"Error in auto-join: {e}")
            await update.message.reply_text(
                f"❌ Error joining game. Please try again or contact the host."
            )

    async def newgame(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Create new game"""
        user = update.effective_user

        # Check if user already has an active game
        active_player = self.player_service.get_active_player(user.id)
        if active_player:
            await update.message.reply_text(
                "⚠️ You're already in an active game. Quit first to create a new one.",
                reply_markup=MenuBuilder.get_player_menu() if not active_player.get("is_host") else MenuBuilder.get_host_menu()
            )
            return

        try:
            game_id, game_code = self.game_service.create_game(user.id, user.first_name)

            # Try to generate QR code
            try:
                bot_info = await context.bot.get_me()
                qr_image, join_url = self.game_service.generate_qr_code(game_code, bot_info.username)

                caption = self.formatter.format_game_creation_message(game_code, user.first_name, join_url)

                await update.message.reply_photo(
                    photo=qr_image,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=MenuBuilder.get_host_menu(game_id)
                )

            except ImportError:
                # QR libraries not available - fall back to text
                await update.message.reply_text(
                    f"🎮 Game created with code **{game_code}**\n"
                    f"Players can join using: `/join {game_code}`",
                    reply_markup=MenuBuilder.get_host_menu(game_id),
                    parse_mode="Markdown"
                )

        except Exception as e:
            logger.error(f"Error creating game: {e}")
            await update.message.reply_text("❌ Error creating game. Please try again.")

    async def join(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Join existing game"""
        if not context.args:
            await update.message.reply_text("Usage: /join <game_code>")
            return

        user = update.effective_user
        game_code = context.args[0].upper()

        try:
            game_id = self.game_service.join_game(game_code, user.id, user.first_name)
            if game_id:
                game = self.game_service.get_game(game_id)
                await update.message.reply_text(
                    f"🎉 Joined game **{game.code}**!\nHost: {game.host_name}",
                    reply_markup=MenuBuilder.get_player_menu(),
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    f"❌ Game '{game_code}' not found or expired."
                )

        except Exception as e:
            logger.error(f"Error joining game: {e}")
            await update.message.reply_text("❌ Error joining game. Please try again.")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show player status"""
        user = update.effective_user
        active_player = self.player_service.get_active_player(user.id)

        if not active_player:
            await update.message.reply_text("⚠️ You're not in any active game.")
            return

        try:
            game = self.game_service.get_game(active_player["game_id"])
            summary = self.transaction_service.get_player_transaction_summary(
                active_player["game_id"], user.id
            )

            status_msg = self.formatter.format_player_status(game, summary, active_player)
            await update.message.reply_text(status_msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error getting status: {e}")
            await update.message.reply_text("❌ Error getting status.")

    async def mygame(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show game overview"""
        user = update.effective_user
        active_player = self.player_service.get_active_player(user.id)

        if not active_player:
            await update.message.reply_text("⚠️ You're not in any active game.")
            return

        try:
            game_status = self.game_service.get_game_status(active_player["game_id"])
            overview_msg = self.formatter.format_game_overview(game_status)
            await update.message.reply_text(overview_msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error getting game overview: {e}")
            await update.message.reply_text("❌ Error getting game overview.")

    async def player_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show player list - Host only"""
        user = update.effective_user
        is_admin = context.user_data.get("admin_auth", False) or context.user_data.get("admin_temp_exit", False)

        if is_admin and context.user_data.get("game_id"):
            game_id = context.user_data["game_id"]
            if context.user_data.get("admin_temp_exit"):
                context.user_data.pop("admin_temp_exit", None)
        else:
            pdoc = self.player_service.get_active_player(user.id)
            if not pdoc or not pdoc.get("is_host"):
                await update.message.reply_text("⚠️ Only hosts can view player list.")
                return
            game_id = pdoc["game_id"]

        try:
            player_data = self.player_service.get_player_list_data(game_id)
            if not player_data:
                await update.message.reply_text("No players in the game yet.")
                return

            player_list_msg = self.formatter.format_player_list(player_data)
            await update.message.reply_text(player_list_msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error getting player list: {e}")
            await update.message.reply_text("❌ Error getting player list.")

    async def host_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show host status - Host only"""
        user = update.effective_user
        is_admin = context.user_data.get("admin_auth", False) or context.user_data.get("admin_temp_exit", False)

        if is_admin and context.user_data.get("game_id"):
            game_id = context.user_data["game_id"]
            if context.user_data.get("admin_temp_exit"):
                context.user_data.pop("admin_temp_exit", None)
        else:
            pdoc = self.player_service.get_active_player(user.id)
            if not pdoc or not pdoc.get("is_host"):
                await update.message.reply_text("⚠️ Only hosts can view status.")
                return
            game_id = pdoc["game_id"]

        try:
            game_status = self.game_service.get_game_status(game_id)
            status_msg = self.formatter.format_host_status(game_status)
            await update.message.reply_text(status_msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error getting host status: {e}")
            await update.message.reply_text("❌ Error getting status.")

    async def share_qr(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Share QR code - Host only"""
        user = update.effective_user
        pdoc = self.player_service.get_active_player(user.id)

        if not pdoc or not pdoc.get("is_host"):
            await update.message.reply_text("⚠️ Only hosts can share QR codes.")
            return

        try:
            game = self.game_service.get_game(pdoc["game_id"])
            bot_info = await context.bot.get_me()
            qr_image, join_url = self.game_service.generate_qr_code(game.code, bot_info.username)

            players = self.player_service.get_players(pdoc["game_id"])
            active_players = [p for p in players if p.active and not p.quit]

            caption = self.formatter.format_qr_share_message(game, user.first_name, len(active_players), join_url)

            await update.message.reply_photo(
                photo=qr_image,
                caption=caption,
                parse_mode="HTML",
                reply_markup=MenuBuilder.get_host_menu(pdoc["game_id"])
            )

        except ImportError:
            await update.message.reply_text("⚠️ QR code generation not available.")
        except Exception as e:
            logger.error(f"Error sharing QR code: {e}")
            await update.message.reply_text("❌ Error generating QR code.")

    async def help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help message"""
        user = update.effective_user
        active_player = self.player_service.get_active_player(user.id)

        if active_player and active_player.get("is_host"):
            help_msg = self.formatter.format_host_help()
            menu = MenuBuilder.get_host_menu()
        elif active_player:
            help_msg = self.formatter.format_player_help()
            menu = MenuBuilder.get_player_menu()
        else:
            help_msg = self.formatter.format_general_help()
            menu = None

        await update.message.reply_text(help_msg, reply_markup=menu, parse_mode="Markdown")

    async def admin_login(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin login command"""
        if not context.args or len(context.args) != 2:
            await update.message.reply_text(
                "🔐 **Admin Login Required**\n\n"
                "Usage: `/admin <username> <password>`",
                parse_mode="Markdown"
            )
            return

        username, password = context.args
        if self.admin_service.authenticate_admin(username, password):
            context.user_data["admin_auth"] = True
            await update.message.reply_text(
                "✅ **Admin Access Granted**\n\nWelcome to admin panel!",
                reply_markup=MenuBuilder.get_admin_menu(),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Invalid admin credentials.")

    async def admin_text_login(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin login via text message"""
        text = update.message.text
        parts = text.split()
        if len(parts) == 3 and parts[0].lower() == "admin":
            username, password = parts[1], parts[2]
            if self.admin_service.authenticate_admin(username, password):
                context.user_data["admin_auth"] = True
                await update.message.reply_text(
                    "✅ **Admin Access Granted**\n\nWelcome to admin panel!",
                    reply_markup=MenuBuilder.get_admin_menu(),
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Invalid admin credentials.")