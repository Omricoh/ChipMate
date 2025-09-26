#!/usr/bin/env python
"""
Script to help stop duplicate bot instances by clearing Telegram webhook/polling
"""

import os
import asyncio
from telegram import Bot

async def clear_webhook():
    """Clear any webhook and stop polling conflicts"""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("TELEGRAM_TOKEN not found!")
        return

    bot = Bot(token=token)

    try:
        # Clear webhook (if any)
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Cleared webhook and dropped pending updates")

        # Get bot info to verify connection
        me = await bot.get_me()
        print(f"✅ Bot @{me.username} is accessible")

    except Exception as e:
        print(f"❌ Error: {e}")

    await bot.close()

if __name__ == "__main__":
    print("🔄 Clearing Telegram webhook and pending updates...")
    asyncio.run(clear_webhook())
    print("✅ Done! You can now start the bot.")