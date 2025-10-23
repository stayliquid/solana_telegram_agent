import logging
import os
import json
import openai
from types import SimpleNamespace

logger = logging.getLogger(__name__)

USE_MOCK_OPENAI = os.getenv("USE_MOCK_OPENAI", "False").lower() in ("true", "1", "t")

class AsyncMockAudioTranscriptions:
    """Mocks the audio.transcriptions part of the OpenAI client."""
    async def create(self, **kwargs):
        logger.info("--- MOCK OPENAI: Returning mock voice transcription ---")
        # The real response has a 'text' attribute. We mimic that.
        mock_transcription = SimpleNamespace(text="Find me a low risk pool with top 50 tokens.")
        return mock_transcription

class AsyncMockChatCompletions:
    """Mocks the chat.completions part of the OpenAI client."""
    async def create(self, **kwargs):
        logger.info("--- MOCK OPENAI: Returning mock chat completion with tool call ---")
        # The real response has a complex nested structure. We mimic it using SimpleNamespace
        # to allow for attribute access like `response.choices[0].message`.
        mock_tool_call = SimpleNamespace(
            function=SimpleNamespace(
                arguments=json.dumps({
                    "risk_level": "low",
                    "market_cap_rank_limit": 50
                })
            )
        )
        mock_message = SimpleNamespace(tool_calls=[mock_tool_call])
        mock_choice = SimpleNamespace(message=mock_message)
        mock_response = SimpleNamespace(choices=[mock_choice])
        return mock_response

class AsyncMockOpenAI:
    """A mock of the openai.AsyncOpenAI client."""
    def __init__(self):
        self.audio = SimpleNamespace(transcriptions=AsyncMockAudioTranscriptions())
        self.chat = SimpleNamespace(completions=AsyncMockChatCompletions())


openai_client = None

if USE_MOCK_OPENAI:
    logger.warning("--- MOCK MODE ENABLED: Using mock OpenAI client. No real API calls will be made. ---")
    openai_client = AsyncMockOpenAI()
else:
    try:
        openai_client = openai.AsyncOpenAI()
        logger.info("Successfully initialized real OpenAI client.")
    except openai.OpenAIError as e:
        logger.error(
            f"Failed to initialize OpenAI client: {e}. "
            "Functions relying on OpenAI (intent parsing, voice transcription) will not work."
        )