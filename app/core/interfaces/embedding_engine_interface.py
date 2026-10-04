from abc import ABC, abstractmethod
from typing import List

class IEmbeddingEngine(ABC):
    @abstractmethod
    def get_embedding(self, text: str) -> List[float]:
        """Generate numerical vector embedding for input text string."""
        pass
