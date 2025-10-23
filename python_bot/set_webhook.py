import asyncio
import os
import sys
from dotenv import load_dotenv

from telegram import Bot

async def main():
    """A simple script to set the Telegram bot's webhook."""
    load_dotenv()
    
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    BASE_WEBHOOK_URL = os.getenv("WEBHOOK_URL")

    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN not found in .env file.", file=sys.stderr)
        return

    if not BASE_WEBHOOK_URL:
        print("Error: WEBHOOK_URL not found in .env file. Please set it to your Vercel or ngrok base URL.", file=sys.stderr)
        return

    # Construct the full webhook URL with the correct endpoint
    full_webhook_url = f"{BASE_WEBHOOK_URL.rstrip('/')}/telegram"

    bot = Bot(token=TELEGRAM_TOKEN)
    
    print(f"Setting webhook to: {full_webhook_url}")
    
    # You can also check current webhook status
    webhook_info = await bot.get_webhook_info()
    print(f"Current webhook info: {webhook_info}")

    # Set the new webhook with the full path
    success = await bot.set_webhook(url=full_webhook_url)

    if success:
        print("Webhook set successfully!")
    else:
        print("Failed to set webhook.", file=sys.stderr)
        
    # Verify it was set correctly
    webhook_info = await bot.get_webhook_info()
    print(f"New webhook info: {webhook_info}")


if __name__ == "__main__":
    asyncio.run(main())