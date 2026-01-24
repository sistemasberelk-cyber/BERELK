from .base import VoiceProvider
from elevenlabs.client import ElevenLabs
import openai
import io

class ElevenLabsVoiceProvider(VoiceProvider):
    def __init__(self, tts_api_key: str, stt_api_key: str = None):
        self.client = ElevenLabs(api_key=tts_api_key)
        # For Premium STT, we often use OpenAI Whisper.
        # We can accept an optional OpenAI key for STT or reuse the one from LLM if passed.
        # For simplicity here, let's assume we might use OpenAI for STT if we are in Premium.
        self.stt_client = openai.AsyncOpenAI(api_key=stt_api_key) if stt_api_key else None

    async def synthesize_speech(self, text: str, voice_id: str = None) -> bytes:
        # Default: Rachel (one of the pre-made voices)
        voice = voice_id or "21m00Tcm4TlvDq8ikWAM" 
        
        audio = self.client.generate(
            text=text,
            voice=voice,
            model="eleven_multilingual_v2"
        )
        
        # Audio is a generator, consume it to bytes
        audio_bytes = b"".join([chunk for chunk in audio])
        return audio_bytes

    async def transcribe_audio(self, audio_content: bytes) -> str:
        # ElevenLabs doesn't do STT. We use OpenAI Whisper as part of the "Premium" Voice stack.
        if not self.stt_client:
            return "" # Or raise Error
        
        try:
            # Whisper expects a file-like object with a name
            audio_file = io.BytesIO(audio_content)
            audio_file.name = "audio.ogg" # WhatsApp format assumption
            
            transcript = await self.stt_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
            return transcript.text
        except Exception as e:
            print(f"Whisper STT Error: {e}")
            return ""
