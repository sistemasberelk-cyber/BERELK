from ..database.models import BusinessConfig
from .llm.base import LLMProvider
from .llm.deepseek_provider import DeepSeekProvider
from .llm.openai_provider import OpenAIProvider
from .voice.base import VoiceProvider
from .voice.google_provider import GoogleVoiceProvider
from .voice.elevenlabs_provider import ElevenLabsVoiceProvider
import os

def get_llm_provider(config: BusinessConfig) -> LLMProvider:
    if config.tier == "premium":
        return OpenAIProvider(api_key=config.openai_api_key or os.getenv("OPENAI_API_KEY"))
    else:
        # Standard - DeepSeek
        return DeepSeekProvider(api_key=config.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY"))

def get_voice_provider(config: BusinessConfig) -> VoiceProvider:
    if config.tier == "premium":
        return ElevenLabsVoiceProvider(
            tts_api_key=config.elevenlabs_api_key or os.getenv("ELEVENLABS_API_KEY"),
            stt_api_key=config.openai_api_key or os.getenv("OPENAI_API_KEY") # Reuse OpenAI for STT
        )
    else:
        # Standard - Google
        return GoogleVoiceProvider()
