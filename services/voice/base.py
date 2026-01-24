from abc import ABC, abstractmethod

class VoiceProvider(ABC):
    @abstractmethod
    async def synthesize_speech(self, text: str, voice_id: str = None) -> bytes:
        """
        Converts text to audio bytes.
        """
        pass

    @abstractmethod
    async def transcribe_audio(self, audio_content: bytes) -> str:
        """
        Converts audio bytes to text.
        """
        pass
