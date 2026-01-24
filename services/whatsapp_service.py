from ..database.models import BusinessConfig
from .provider_factory import get_llm_provider, get_voice_provider

class WhatsAppService:
    async def process_message(self, content: bytes | str, config: BusinessConfig) -> bytes:
        """
        Process an incoming message (audio bytes or text string) and return a voice response (audio bytes).
        """
        
        voice_provider = get_voice_provider(config)
        llm_provider = get_llm_provider(config)
        
        # 1. Transcribe (if audio) or Use Text
        user_text = ""
        if isinstance(content, bytes):
            # It's an audio file
            user_text = await voice_provider.transcribe_audio(content)
            print(f"Transcribed: {user_text}")
        else:
            user_text = content
            print(f"Received Text: {user_text}")

        if not user_text:
            return b"" # Or some error audio
            
        # 2. Get AI Response
        ai_text = await llm_provider.generate_response(user_text, config.system_prompt)
        print(f"AI Response: {ai_text}")
        
        # 3. Synthesize Speech
        response_audio = await voice_provider.synthesize_speech(ai_text, config.voice_id)
        
        return response_audio
