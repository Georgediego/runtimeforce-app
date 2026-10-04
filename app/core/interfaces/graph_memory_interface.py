"""
Abstract interface for Graph Memory Architecture and Knowledge Graph management.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class IGraphMemory(ABC):

    @abstractmethod
    def add_node(
        self,
        node_id: str,
        user_id: str,
        project_id: str,
        node_type: str,
        label: str,
        attributes: Optional[Dict[str, Any]] = None,
        importance: float = 1.0
    ) -> bool:
        """Add or update a knowledge node in the project graph."""
        pass

    @abstractmethod
    def add_edge(
        self,
        edge_id: str,
        source_id: str,
        target_id: str,
        relation_type: str,
        weight: float = 1.0
    ) -> bool:
        """Create an explicit directed relationship edge between two nodes."""
        pass

    @abstractmethod
    def query_subgraph(
        self,
        project_id: str,
        user_id: str,
        root_node_types: Optional[List[str]] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Traverse and return connected subgraph nodes and edges."""
        pass

    @abstractmethod
    def rank_nodes(
        self,
        nodes: List[Dict[str, Any]],
        query_text: str
    ) -> List[Dict[str, Any]]:
        """Rank nodes based on Relevance, Freshness, Importance, and Usage Count."""
        pass
