Create a `.env` file in the `python-bot` directory with the following content:

```
# Telegram Bot Token from @BotFather
TELEGRAM_TOKEN="YOUR_TELEGRAM_TOKEN"

# Publicly accessible URL for the python-bot (port 8000)
# e.g., from ngrok: https://xxxx-xx-xxx-xx-xx.ngrok-free.app
WEBHOOK_URL="YOUR_PYTHON_BOT_WEBHOOK_URL"

# Publicly accessible URL for the tx-builder-service (port 3001)
# e.g., from a separate ngrok tunnel: https://yyyy-yy-yyy-yy-yy.ngrok-free.app
TX_BUILDER_URL="YOUR_TX_BUILDER_SERVICE_URL"

# OpenAI API Key for intent parsing and voice transcription
OPENAI_API_KEY="sk-..."

# CoinMarketCap API Key for fetching token rankings
COINMARKETCAP_API_KEY="YOUR_CMC_API_KEY"

# Optional: Set to "true" to use mock data for testing without API calls
# USE_MOCK_OPENAI=false
```

### 2. Install Dependencies

In the `python-bot` directory:
```bash
pip install -r requirements.txt
```

## Running the Application

### Expose Services with ngrok

You need to expose both services to the internet for Telegram webhooks and Solana Actions to work.

Expose the Python bot (port 8000):
```bash
ngrok http 8000
```
Copy the `https://...ngrok-free.app` URL and set it as `WEBHOOK_URL` in `python-bot/.env`.

### Terminal 3: Start the Python Bot

With the `.env` file correctly configured with your ngrok URLs, start the bot.

```bash
cd python-bot
uvicorn main:api --host 0.0.0.0 --port 8000
```

Your bot is now live and ready to use in Telegram!
```
