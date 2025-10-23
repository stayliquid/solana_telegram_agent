import os
import asyncio
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from bot.handlers import start_handler,  text_and_voice_handler, button_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is not set in the environment!")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is not set! Get it from ngrok and add it to .env")


# --- Telegram Bot Application Setup ---
def setup_application() -> Application:
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(MessageHandler(filters.TEXT | filters.VOICE, text_and_voice_handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    return application

application = setup_application()


# --- FastAPI Lifespan and Webhook Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing bot and setting webhook...")
    await application.initialize()
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    
    yield

    logger.info("Shutting down bot and deleting webhook...")
    await application.shutdown()
    await application.bot.delete_webhook()


# --- FastAPI App and Endpoints ---
api = FastAPI(lifespan=lifespan)

@api.post("/telegram")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates by passing them to the bot application."""
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        
        await application.process_update(update)
        
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error processing update: {e}", exc_info=True)
        return Response(status_code=500)

@api.get("/")
async def health_check():
    """A simple health check endpoint to verify the server is running."""
    return {"status": "ok"}

@api.get("/redirect", response_class=HTMLResponse)
async def redirect_to_solana_action(target: str):
    """
    Redirects the user to a Solana Action link from a standard HTTP link.
    This is a workaround for Telegram buttons not supporting custom URL schemes.
    """
    # Basic validation to prevent open redirect vulnerabilities
    if not target.startswith("solana-action:"):
        return HTMLResponse("Invalid target URL.", status_code=400)

    import html
    safe_target = html.escape(target, quote=True)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Redirecting...</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="refresh" content="0; url={safe_target}" />
        <style>
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
                display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;
                background-color: #1c1c1e; color: #f2f2f7;
            }}
            .container {{ 
                text-align: center; padding: 30px; background: #2c2c2e; 
                border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            }}
            h2 {{ margin-top: 0; }}
            a {{ color: #5856d6; text-decoration: none; font-weight: bold; }}
        </style>
        <script type="text/javascript">
            window.location.href = "{safe_target}";
        </script>
    </head>
    <body>
        <div class="container">
            <h2>Launching Wallet...</h2>
            <p>If you are not redirected automatically, please<br/><a href="{safe_target}">click here to open the transaction</a>.</p>
        </div>
    </body>
    </html>
    """
