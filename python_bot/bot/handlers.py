import logging
import os
import tempfile
import json
import base64
import re
from urllib.parse import quote
from pydub import AudioSegment
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes

from python_bot.core.agent import parse_intent_from_text
from python_bot.core.engine import find_and_propose_pool
from python_bot.core.openai_client import openai_client
from python_bot.core.raydium_helpers import get_clmm_deposit_amounts
from python_bot.bot.utils import escape_markdown_v2

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

USE_MOCK_VOICE = os.getenv("USE_MOCK_VOICE_TRANSCRIPTION", "False").lower() in ("true", "1", "t")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TX_BUILDER_URL = os.getenv("TX_BUILDER_URL")


# --- Helper Functions ---

async def _get_user_input_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """
    Extracts text from a message, transcribing voice if necessary.
    Returns the text string or None if no valid input is found or an error occurs.
    """
    if update.message.voice:
        user = update.effective_user
        logger.info(f"Received voice memo from {user.username}.")
        
        if USE_MOCK_VOICE:
            logger.info("--- MOCK: Using fake voice transcription as per .env flag ---")
            return "Fake prompt from voice memo."
        
        if not openai_client:
            await update.message.reply_text("Sorry, voice message processing is not configured on the server.")
            return None

        try:
            voice_file = await context.bot.get_file(update.message.voice.file_id)
            with tempfile.TemporaryDirectory() as temp_dir:
                oga_path = os.path.join(temp_dir, "voice.oga")
                mp3_path = os.path.join(temp_dir, "voice.mp3")
                await voice_file.download_to_drive(oga_path)
                audio = AudioSegment.from_file(oga_path)
                audio.export(mp3_path, format="mp3")
                with open(mp3_path, "rb") as audio_file:
                    transcription = await openai_client.audio.transcriptions.create(model="whisper-1", file=audio_file)
                logger.info(f"Transcription result: '{transcription.text}'")
                return transcription.text
        except Exception as e:
            logger.error(f"Error processing voice message: {e}", exc_info=True)
            await update.message.reply_text("Sorry, I had trouble understanding your voice memo. Please try again or send a text message.")
            return None
    
    elif update.message.text:
        user = update.effective_user
        logger.info(f"Received text from {user.username}: {update.message.text}")
        return update.message.text
    
    return None

async def _send_thinking_message(update: Update) -> Message:
    """Sends a standardized 'thinking' message and returns the message object."""
    return await update.message.reply_text(
        "🧠 Thinking..."
    )

def _parse_amount_from_text(text: str) -> float | None:
    """Finds the first valid number (integer or float) in a string."""
    # This regex is improved to avoid capturing version numbers like "v2" or trailing dots.
    numbers = re.findall(r"(?<![a-zA-Z])\b(\d+\.?\d*|\.\d+)\b(?![a-zA-Z])", text)
    if numbers:
        try:
            num = float(numbers[0])
            return num if num > 0 else None
        except (ValueError, IndexError):
            return None
    return None

async def _send_final_link(message_to_edit: Message, context: ContextTypes.DEFAULT_TYPE, pool_id: str, amount: float):
    """Generates the final dial.to transaction link and edits the provided message."""
    proposal_info = context.user_data.get('proposals', {}).get(pool_id)
    if not proposal_info or "data" not in proposal_info:
        logger.warning(f"Final link generation failed: Proposal {pool_id} not found for user.")
        await message_to_edit.edit_text(text="Sorry, this proposal has expired. Please send your request again.")
        return

    proposal = proposal_info["data"]

    if not TX_BUILDER_URL:
        logger.error("TX_BUILDER_URL is not set!")
        await message_to_edit.edit_text("Sorry, the bot is not configured correctly to build transactions.")
        return

    try:
        proposal_json = json.dumps(proposal)
        action_id = base64.urlsafe_b64encode(proposal_json.encode('utf-8')).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to encode proposal: {e}")
        await message_to_edit.edit_text("Sorry, there was a problem generating your transaction link.")
        return
    
    action_api_url = f"{TX_BUILDER_URL.rstrip('/')}/api/actions/join-pool/{action_id}?amount={amount}"
    solana_action_uri = f"solana-action:{action_api_url}"
    encoded_solana_action_uri = quote(solana_action_uri)
    final_url = f"https://dial.to/?action={encoded_solana_action_uri}"

    logger.info(f"Generated dial.to URL: {final_url}")

    pool_name = escape_markdown_v2(proposal["pool_name"])
    liquidity_str = escape_markdown_v2(f"${proposal['liquidity']:,.0f}")
    volume_str = escape_markdown_v2(f"${proposal.get('volume_24h', 0):,.0f}")
    input_token_symbol = escape_markdown_v2(proposal.get("raw_proposal", {}).get("mintA", {}).get("symbol", "tokens"))
    amount_str = escape_markdown_v2(f"{amount:g}")
    apy_str = escape_markdown_v2(f"{proposal['apy']:.2%}")

    message_text = (
        f"✅ Great\\! You're depositing *{amount_str} {input_token_symbol}* into the `{pool_name}` pool\\.\n\n"
        f"🔹 *Liquidity:* {liquidity_str}\n"
        f"🔹 *Volume \\(24h\\):* {volume_str}\n"
        f"🔹 *APY \\(24h\\):* {apy_str}\n\n"
        f"Click the button below to open your wallet and confirm the transaction\\."
    )
    
    keyboard = [[InlineKeyboardButton("🚀 Add Liquidity", url=final_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message_to_edit.edit_text(
        text=message_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

# --- State Handlers ---

async def _handle_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE, user_input_text: str):
    """Handles the user's message when the bot is expecting an amount."""
    pool_id = context.user_data.get('pending_pool_id')
    if not pool_id:
        await update.message.reply_text("Something went wrong. Please start your query again.")
        context.user_data['state'] = None
        context.user_data['pending_pool_id'] = None
        return

    amount = _parse_amount_from_text(user_input_text)
    
    if amount:
        logger.info(f"Received amount {amount} for pending pool {pool_id}.")
        context.user_data['state'] = None
        context.user_data['pending_pool_id'] = None
        placeholder_message = await update.message.reply_text("Got it. Preparing your transaction...")
        await _send_final_link(placeholder_message, context, pool_id, amount)
    else:
        logger.warning(f"Invalid amount input from user: '{user_input_text}'")
        proposal_info = context.user_data.get('proposals', {}).get(pool_id, {})
        proposal = proposal_info.get("data", {})
        token_symbol = proposal.get("raw_proposal", {}).get("mintA", {}).get("symbol", "tokens")
        await update.message.reply_text(
            f"That doesn't seem to be a valid amount. Please reply with just the number of *{escape_markdown_v2(token_symbol)}* you want to deposit (e.g., 10.5).",
            parse_mode="MarkdownV2"
        )

async def _handle_new_query(update: Update, context: ContextTypes.DEFAULT_TYPE, user_input_text: str):
    """Handles a new query for a liquidity pool, taking transcribed text as input."""
    user = update.effective_user
    if not user_input_text:
        return

    thinking_message = await _send_thinking_message(update)
    intent, conversational_response = await parse_intent_from_text(user_input_text)

    if conversational_response:
        await thinking_message.edit_text(text=conversational_response)
        return

    if not intent:
        await thinking_message.edit_text(
            text="❌ Sorry, I couldn't understand the specific criteria from your message. "
                 "Could you try rephrasing? For example: 'Find a medium-risk pool with top 20 tokens.'"
        )
        return

    proposal = await find_and_propose_pool(intent)

    if not proposal:
        await thinking_message.edit_text(
            text="😔 I couldn't find any pools that match your criteria. "
                 "Try adjusting your request, for example, by asking for a higher risk level."
        )
        return

    pool_id = proposal["pool_id"]
    if 'proposals' not in context.user_data:
        context.user_data['proposals'] = {}
    
    pool_name = escape_markdown_v2(proposal["pool_name"])
    liquidity_str = escape_markdown_v2(f"${proposal['liquidity']:,.0f}")
    apy_str = escape_markdown_v2(f"{proposal['apy']:.2%}")
    volume_str = escape_markdown_v2(f"${proposal.get('volume_24h', 0):,.0f}")
    
    details_text = (
        f"✅ I found a great option for you\\! Here are the details:\n\n"
        f"🔹 *Pool:* `{pool_name}`\n"
        f"🔹 *Liquidity:* {liquidity_str}\n"
        f"🔹 *Volume \\(24h\\):* {volume_str}\n"
        f"🔹 *APY \\(24h\\):* {apy_str}"
    )
    
    message_text = f"{details_text}\n\nDo you want to proceed with this pool?"
    
    context.user_data['proposals'][pool_id] = {
        "data": proposal,
        "details_text_md2": details_text,
    }
    logger.info(f"Stored proposal {pool_id} for user {user.id}. Amount will be requested after confirmation.")
    
    keyboard = [[
        InlineKeyboardButton("✅ Yes, accept", callback_data=f"accept:{pool_id}"),
        InlineKeyboardButton("❌ No, reject", callback_data=f"reject:{pool_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    edited_message = await thinking_message.edit_text(text=message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")

    context.user_data['proposals'][pool_id]['message_id'] = edited_message.message_id
    context.user_data['state'] = 'awaiting_proposal_response'


# --- Main Telegram Handlers ---

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message with instructions."""
    user = update.effective_user
    logger.info(f"User {user.username} started the bot.")
    welcome_message = (
        f"Hi {user.mention_html()}! I find the highest APY liquidity pools on Solana based on your risk preferences.\n\n"
        "Just tell me what you're looking for. You can specify:\n\n"
        "🔹 **Risk Level**: `low`, `medium`, or `high`\n"
        "🔹 **Token Rank**: e.g., `top 50 tokens`\n\n"
        "<b>Try one of these examples (text or voice):</b>\n"
        "• Find a low risk pool\n"
        "• Show me high risk pools with top 20 tokens"
    )
    await update.message.reply_html(welcome_message)

async def text_and_voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Routes incoming text and voice messages to the correct handler based on bot state."""
    user_input_text = await _get_user_input_text(update, context)
    if not user_input_text:
        return

    current_state = context.user_data.get('state')

    if current_state == 'awaiting_amount':
        await _handle_amount_input(update, context, user_input_text)
        return

    if current_state == 'awaiting_proposal_response':
        amount = _parse_amount_from_text(user_input_text)
        rejection_keywords = ["no", "reject", "different", "another", "cancel", "stop"]
        contains_rejection = any(kw in user_input_text.lower() for kw in rejection_keywords)

        if amount and not contains_rejection:
            logger.info(f"User accepted with amount '{amount}' via text/voice.")
            proposals = context.user_data.get('proposals', {})
            active_pool_id = next((pid for pid, p in proposals.items() if 'message_id' in p), None)
            
            if active_pool_id:
                p_info = proposals[active_pool_id]
                await context.bot.edit_message_text(text=p_info.get('details_text_md2'), chat_id=update.message.chat_id, message_id=p_info.get('message_id'), parse_mode="MarkdownV2", reply_markup=None)
                placeholder = await update.message.reply_text("Got it. Preparing your transaction...")
                await _send_final_link(placeholder, context, active_pool_id, amount)
                context.user_data['state'] = None
                context.user_data.get('proposals', {}).pop(active_pool_id, None)
                return

        logger.info("Message received while awaiting proposal response was not a direct acceptance. Treating as new query.")
        context.user_data['state'] = None

    await _handle_new_query(update, context, user_input_text)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the user's response to a pool suggestion."""
    query = update.callback_query
    await query.answer()

    action, pool_id = query.data.split(":", 1)
    proposal_info = context.user_data.get('proposals', {}).get(pool_id)
    if not proposal_info:
        await query.edit_message_text("Sorry, this proposal has expired. Please send your request again.")
        return
    
    details_text = proposal_info.get('details_text_md2')
    await query.edit_message_text(text=details_text, parse_mode="MarkdownV2", reply_markup=None)

    if action == "reject":
        await context.bot.send_message(chat_id=query.message.chat_id, text="Please send another message to find a different pool.")
        context.user_data['state'] = None
        return

    if action == "accept":
        proposal = proposal_info["data"]
        token_symbol = proposal.get("raw_proposal", {}).get("mintA", {}).get("symbol", "tokens")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"Please reply with the amount of *{escape_markdown_v2(token_symbol)}* you would like to deposit\\.",
            parse_mode="MarkdownV2"
        )
        context.user_data['state'] = 'awaiting_amount'
        context.user_data['pending_pool_id'] = pool_id