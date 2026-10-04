"""
BYOK OpenAI Driver

Implements LLM provider interface for OpenAI API.
Supports chat completions with streaming.
"""

from typing import AsyncGenerator, Dict, Any, Optional, List
import aiohttp
import logging

from app.core.interfaces.llm_provider_interface import ILLMProvider

logger = logging.getLogger(__name__)


class BYOKOpenAIDriver(ILLMProvider):
    """OpenAI API provider implementation for BYOK."""

    PROVIDER_NAME = "openai"
    BASE_URL = "https://api.openai.com/v1"

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url or self.BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
        return self.session

    async def close(self):
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def stream_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat completion from OpenAI API.

        Args:
            model: Model name (e.g., 'gpt-4', 'gpt-3.5-turbo')
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            frequency_penalty: Frequency penalty
            presence_penalty: Presence penalty
            **kwargs: Additional parameters

        Yields:
            Content chunks as strings
        """
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            "stream": True
        }

        # Add any additional parameters
        payload.update(kwargs)

        session = await self._get_session()

        try:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"OpenAI API error: {response.status} - {error_text}")
                    raise Exception(f"OpenAI API error: {response.status}")

                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data = line[6:]
                        if data == '[DONE]':
                            break

                        try:
                            import json
                            chunk = json.loads(data)
                            choices = chunk.get('choices', [])
                            if choices:
                                delta = choices[0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            logger.error(f"Error in OpenAI stream: {e}")
            raise

    async def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any
    ) -> str:
        """
        Non-streaming chat completion.

        Args:
            model: Model name
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            Complete response text
        """
        full_response = ""
        async for chunk in self.stream_chat_completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        ):
            full_response += chunk

        return full_response

    async def validate_connection(self) -> bool:
        """Test API key validity with a minimal request."""
        try:
            response = await self.chat_completion(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            return len(response) > 0
        except Exception:
            return False

    def get_supported_models(self) -> List[str]:
        """Return list of supported OpenAI models."""
        return [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-3.5-turbo",
            "o1-preview",
            "o1-mini"
        ]
