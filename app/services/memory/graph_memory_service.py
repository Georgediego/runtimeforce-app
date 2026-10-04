"""
Service for Managing Knowledge Graph Entities, Auto-Relations, and Working Memory.
"""
import uuid
import logging
from typing import Dict, Any, List, Optional
from app.repository.graph_db_repository import GraphDBRepository
from app.repository.embeddings_db_repository import EmbeddingsDBRepository

logger = logging.getLogger("runtimeforce.service.memory.graph")

class GraphMemoryService:
    def __init__(self, graph_repo: GraphDBRepository, embeddings_repo: EmbeddingsDBRepository):
        self.graph_repo = graph_repo
        self.embeddings_repo = embeddings_repo

    def record_entity(
        self,
        node_id: str,
        user_id: str,
        project_id: str,
        node_type: str,
        label: str,
        attributes: Optional[Dict[str, Any]] = None,
        text_for_search: str = ""
    ) -> bool:
        success = self.graph_repo.add_node(node_id, user_id, project_id, node_type, label, attributes)
        if success and text_for_search:
            self.embeddings_repo.index_text(node_id, text_for_search)
        return success

    def link_entities(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        weight: float = 1.0
    ) -> bool:
        edge_id = f"edge-{uuid.uuid4().hex[:8]}"
        return self.graph_repo.add_edge(edge_id, source_id, target_id, relation_type, weight)

    def get_working_memory_context(
        self,
        project_id: str,
        user_id: str,
        query: str = ""
    ) -> Dict[str, Any]:
        subgraph = self.graph_repo.query_subgraph(project_id, user_id, limit=20)
        ranked = self.graph_repo.rank_nodes(subgraph.get("nodes", []), query)
        
        hybrid_results = self.embeddings_repo.hybrid_search(query, project_id, top_k=5) if query else []

        return {
            "top_nodes": ranked[:10],
            "hybrid_search": hybrid_results,
            "edges": subgraph.get("edges", [])
        }
