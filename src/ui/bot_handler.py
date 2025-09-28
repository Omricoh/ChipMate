"""
Telegram Bot Handler - UI Layer
Handles all Telegram bot interactions and message routing
"""
import logging
from telegram.ext import Application

from src.ui.handlers.command_handlers import CommandHandlers
from src.ui.handlers.conversation_handlers import ConversationHandlers
from src.ui.handlers.callback_handlers import CallbackHandlers
from src.bl.game_service import GameService
from src.bl.player_service import PlayerService
from src.bl.transaction_service import TransactionService
from src.bl.admin_service import AdminService

logger = logging.getLogger("chipbot")

class ChipBotHandler:
    """Main bot handler that coordinates all UI components"""

    def __init__(self, token: str, mongo_url: str):
        self.token = token
        self.mongo_url = mongo_url
        self.app = None

        # Initialize services
        self.game_service = GameService(mongo_url)
        self.player_service = PlayerService(mongo_url)
        self.transaction_service = TransactionService(mongo_url)
        self.admin_service = AdminService(mongo_url)

    def setup_handlers(self):
        """Setup all bot handlers"""
        # Initialize handler classes
        command_handlers = CommandHandlers(
            self.game_service,
            self.player_service,
            self.transaction_service,
            self.admin_service
        )

        conversation_handlers = ConversationHandlers(
            self.game_service,
            self.player_service,
            self.transaction_service,
            self.admin_service
        )

        callback_handlers = CallbackHandlers(
            self.game_service,
            self.player_service,
            self.transaction_service,
            self.admin_service
        )

        # Register all handlers
        command_handlers.register_handlers(self.app)
        conversation_handlers.register_handlers(self.app)
        callback_handlers.register_handlers(self.app)

    def setup_job_queue(self):
        """Setup periodic jobs"""
        try:
            # Auto-expire old games every hour
            if self.app.job_queue:
                self.app.job_queue.run_repeating(
                    self.admin_service.expire_old_games_job,
                    interval=3600,
                    first=10
                )
                logger.info("Job queue set up successfully")
        except Exception as e:
            logger.warning(f"Could not set up job queue: {e}")

    def run(self):
        """Run the bot"""
        try:
            # Create application
            self.app = Application.builder().token(self.token).build()

            # Setup handlers and jobs
            self.setup_handlers()
            self.setup_job_queue()

            logger.info("ChipBot starting...")

            # Run the bot
            self.app.run_polling(drop_pending_updates=True, close_loop=False)

        except Exception as e:
            logger.error(f"Bot error: {e}")
        finally:
            logger.info("ChipBot shutting down...")