from .base import VoiceProvider
from google.cloud import texttospeech
from google.cloud import speech

class GoogleVoiceProvider(VoiceProvider):
    def __init__(self):
        # Assumes GOOGLE_APPLICATION_CREDENTIALS env var is set
        self.tts_client = texttospeech.TextToSpeechClient()
        self.stt_client = speech.SpeechClient()

    async def synthesize_speech(self, text: str, voice_id: str = None) -> bytes:
        input_text = texttospeech.SynthesisInput(text=text)
        
        # Default voice config - Standard Spanish
        voice = texttospeech.VoiceSelectionParams(
            language_code="es-ES",
            name=voice_id or "es-ES-Standard-A"
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        response = self.tts_client.synthesize_speech(
            input=input_text, voice=voice, audio_config=audio_config
        )
        return response.audio_content

    async def transcribe_audio(self, audio_content: bytes) -> str:
        audio = speech.RecognitionAudio(content=audio_content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS, # WhatsApp usually sends OGG
            sample_rate_hertz=16000, # Typical for WhatsApp voice notes
            language_code="es-ES"
        )
        
        # Note: Handling OGG might require ffmpeg conversion first depending on Google API strictness
        # For now, we assume we might need a converter service intermediate step.
        # But let's stick to the API interface.
        
        try:
             # In a real scenario, we might need to convert OGG to Linear16 or FLAC
            response = self.stt_client.recognize(config=config, audio=audio)
            if not response.results:
                return ""
            return response.results[0].alternatives[0].transcript
        except Exception as e:
            print(f"Google STT Error: {e}")
            return ""
