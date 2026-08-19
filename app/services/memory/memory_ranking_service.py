"""
Memory Ranking Engine implementing exact mathematical scoring:
Score = w_rel * Relevance + w_fresh * e^(-decay * dt) + w_imp * Importance + w_usage * log(1 + Usage)
"""
import math
import time
from typing import List, Dict, Any
from app.services.memory.embedding_engine_service import EmbeddingEngineService

HALF_LIFE_SECONDS = 86400.0 # 24 hours decay

class MemoryRankingService:
    @classmethod
    def rank_nodes(
        cls,
        nodes: List[Dict[str, Any]],
        query_text: str,
        query_vector: List[float] = None
    ) -> List[Dict[str, Any]]:
        if not nodes:
            return []

        if not query_vector and query_text:
            query_vector = EmbeddingEngineService.generate_embedding(query_text)

        now = time.time()

        for node in nodes:
            # 1. Relevance Score (Hybrid BM25 Keyword + Cosine Similarity)
            node_vec = node.get("vector", [])
            cos_sim = EmbeddingEngineService.cosine_similarity(query_vector, node_vec) if query_vector and node_vec else 0.0
            
            label_text = str(node.get("label", "")).lower()
            query_words = set(query_text.lower().split()) if query_text else set()
            keyword_matches = sum(1 for w in query_words if w in label_text)
            bm25_approx = min(1.0, keyword_matches * 0.3)
            
            relevance = (0.6 * cos_sim) + (0.4 * bm25_approx)

            # 2. Freshness Score Exponential Decay: e^(-dt / tau)
            last_used = float(node.get("last_used_timestamp", now))
            dt = max(0.0, now - last_used)
            freshness = math.exp(-dt / HALF_LIFE_SECONDS)

            # 3. Importance & Usage Score
            importance = float(node.get("score_importance", 1.0))
            usage_count = int(node.get("usage_count", 1))
            usage_score = math.log1p(usage_count) / 5.0

            # Combined Score Formula
            node["final_score"] = (relevance * 0.40) + (freshness * 0.25) + (importance * 0.20) + (usage_score * 0.15)

        nodes.sort(key=lambda x: x.get("final_score", 0.0), reverse=True)
        return nodes
