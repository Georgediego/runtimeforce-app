"""
Abstract interface for external and local LLM execution providers.
"""
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

class ILLMProvider(ABC):

    @abstractmethod
    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream LLM text and tool call chunks asynchronously."""
        pass
