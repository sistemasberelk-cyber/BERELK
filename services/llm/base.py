from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def generate_response(self, prompt: str, system_setup: str) -> str:
        """
        Generates a text response from the LLM based on the user prompt and system setup.
        """
        pass
