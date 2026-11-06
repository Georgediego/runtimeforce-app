"""
Incremental Context Cache Service.
Stores last query state and full nodes per session to compute context deltas accurately.
"""
import time
import logging
from typing import List, Dict, Any, Tuple, Optional
from app.services.memory.embedding_engine_service import EmbeddingEngineService

logger = logging.getLogger("runtimeforce.service.memory.context_cache")

class ContextCacheService:
    def __init__(self, similarity_threshold: float = 0.8):
        self.threshold = similarity_threshold
        self._cache: Dict[str, Dict[str, Any]] = {}

    def invalidate_session(self, session_id: str) -> None:
        self._cache.pop(session_id, None)

    def get_delta_context(
        self,
        user_prompt: str,
        session_id: str,
        current_top_nodes: List[Dict[str, Any]]
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        cached = self._cache.get(session_id)
        if not cached:
            return False, current_top_nodes

        cached_prompt = cached.get("prompt", "")
        cached_vec = cached.get("vector", [])
        cached_node_ids = set(cached.get("node_ids", []))
        cached_nodes = cached.get("nodes", [])

        current_vec = EmbeddingEngineService.generate_embedding(user_prompt)
        similarity = EmbeddingEngineService.cosine_similarity(current_vec, cached_vec)

        if similarity >= self.threshold:
            delta_nodes = [n for n in current_top_nodes if n.get("id") not in cached_node_ids]
            combined = cached_nodes + delta_nodes
            logger.info(f"Context Cache HIT (similarity={similarity:.2f}). Returning {len(combined)} nodes ({len(cached_nodes)} cached + {len(delta_nodes)} delta).")
            return True, combined

        return False, current_top_nodes

    def update_cache(
        self,
        session_id: str,
        user_prompt: str,
        top_nodes: List[Dict[str, Any]]
    ) -> None:
        vector = EmbeddingEngineService.generate_embedding(user_prompt)
        node_ids = [n.get("id") for n in top_nodes if n.get("id")]
        self._cache[session_id] = {
            "prompt": user_prompt,
            "vector": vector,
            "node_ids": node_ids,
            "nodes": top_nodes,
            "timestamp": time.time()
        }
