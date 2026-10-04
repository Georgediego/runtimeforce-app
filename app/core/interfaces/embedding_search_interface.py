"""
Abstract interface for Hybrid Search (Semantic + Keyword + Graph Traversal).
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List

class IEmbeddingSearch(ABC):

    @abstractmethod
    def index_text(
        self,
        node_id: str,
        text_content: str
    ) -> bool:
        """Generate and store embedding/keyword index for a graph node."""
        pass

    @abstractmethod
    def hybrid_search(
        self,
        query: str,
        project_id: str,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Perform hybrid semantic, keyword, and graph traversal search."""
        pass
