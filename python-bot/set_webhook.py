import asyncio
import os
import sys
from dotenv import load_dotenv

from telegram import Bot

async def main():
    """A simple script to set the Telegram bot's webhook."""
    load_dotenv()
    
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")

    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN not found in .env file.", file=sys.stderr)
        return

    if not WEBHOOK_URL:
        print("Error: WEBHOOK_URL not found in .env file. Please set it to your Vercel deployment URL.", file=sys.stderr)
        return

    bot = Bot(token=TELEGRAM_TOKEN)
    
    print(f"Setting webhook to: {WEBHOOK_URL}")
    
    # You can also check current webhook status
    webhook_info = await bot.get_webhook_info()
    print(f"Current webhook info: {webhook_info}")

    # Set the new webhook
    success = await bot.set_webhook(url=WEBHOOK_URL)

    if success:
        print("Webhook set successfully!")
    else:
        print("Failed to set webhook.", file=sys.stderr)
        
    # Verify it was set
    webhook_info = await bot.get_webhook_info()
    print(f"New webhook info: {webhook_info}")


if __name__ == "__main__":
    asyncio.run(main())