import os
import openai
from .base import LLMProvider

class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com/v1" # Verify exact DeepSeek API URL
        )

    async def generate_response(self, prompt: str, system_setup: str) -> str:
        try:
            response = await self.client.chat.completions.create(
                model="deepseek-chat", # Check specific model name
                messages=[
                    {"role": "system", "content": system_setup},
                    {"role": "user", "content": prompt}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"DeepSeek Error: {e}")
            return "Lo siento, hubo un error procesando tu solicitud."
