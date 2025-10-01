"""
ChipMate Bot - Main Entry Point
Simple poker game management bot for Telegram
"""
import os
import logging
from src.ui.bot_handler import ChipBotHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("chipbot")

def main():
    """Main application entry point"""
    # Get configuration from environment
    token = os.getenv("TELEGRAM_TOKEN")
    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")

    if not token:
        logger.error("TELEGRAM_TOKEN environment variable not set!")
        return

    # Initialize and run bot
    bot_handler = ChipBotHandler(token, mongo_url)
    bot_handler.run()

if __name__ == "__main__":
    main()