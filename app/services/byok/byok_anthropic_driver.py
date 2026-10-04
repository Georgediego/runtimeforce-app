"""
BYOK Anthropic Driver

Implements LLM provider interface for Anthropic Claude API.
Supports chat completions with streaming.
"""

from typing import AsyncGenerator, Dict, Any, Optional, List
import aiohttp
import logging

from app.core.interfaces.llm_provider_interface import ILLMProvider

logger = logging.getLogger(__name__)


class BYOKAnthropicDriver(ILLMProvider):
    """Anthropic Claude API provider implementation for BYOK."""

    PROVIDER_NAME = "anthropic"
    BASE_URL = "https://api.anthropic.com/v1"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url or self.BASE_URL
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": self.API_VERSION
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
        **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat completion from Anthropic API.

        Args:
            model: Model name (e.g., 'claude-3-opus-20240229')
            messages: List of message dictionaries
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            **kwargs: Additional parameters

        Yields:
            Content chunks as strings
        """
        url = f"{self.base_url}/messages"

        # Convert messages to Anthropic format
        system_message = None
        anthropic_messages = []

        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if role == 'system':
                system_message = content
            else:
                anthropic_messages.append({
                    "role": "assistant" if role == 'assistant' else "user",
                    "content": content
                })

        payload = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True
        }

        if system_message:
            payload["system"] = system_message

        # Add any additional parameters
        payload.update(kwargs)

        session = await self._get_session()

        try:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Anthropic API error: {response.status} - {error_text}")
                    raise Exception(f"Anthropic API error: {response.status}")

                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data = line[5:]
                        if data == '[DONE]':
                            break

                        try:
                            import json
                            chunk = json.loads(data)
                            event_type = chunk.get('type', '')

                            if event_type == 'content_block_delta':
                                delta = chunk.get('delta', {})
                                text = delta.get('text', '')
                                if text:
                                    yield text
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            logger.error(f"Error in Anthropic stream: {e}")
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
                model="claude-3-haiku-20240307",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            return len(response) > 0
        except Exception:
            return False

    def get_supported_models(self) -> List[str]:
        """Return list of supported Anthropic models."""
        return [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022"
        ]
