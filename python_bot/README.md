Steps to run:

Start ngrok in a tab:
`ngrok http 8000`
Run uvicorn in another tab:
`uvicorn main:api --host 0.0.0.0 --port 8000`
Bot is live!
