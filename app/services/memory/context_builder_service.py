"""
Complete Context Builder Pipeline with Fixed Cache Check & Hybrid Search.
"""
import logging
from typing import Dict, Any, List, Optional
from app.core.interfaces.context_builder_interface import IContextBuilder
from app.services.memory.graph_memory_service import GraphMemoryService
from app.services.memory.graph_traversal_service import GraphTraversalService
from app.services.memory.context_cache_service import ContextCacheService
from app.services.memory.intent_analyzer_service import IntentAnalyzerService
from app.services.memory.memory_ranking_service import MemoryRankingService
from app.services.memory.token_budget_allocator import TokenBudgetAllocator
from app.repository.decision_db_repository import DecisionDBRepository
from app.repository.embeddings_db_repository import EmbeddingsDBRepository

logger = logging.getLogger("runtimeforce.service.memory.context_builder")


class ContextBuilderService(IContextBuilder):
    def __init__(
        self,
        graph_memory: GraphMemoryService,
        decision_repo: DecisionDBRepository,
        graph_traversal: GraphTraversalService,
        context_cache: ContextCacheService,
        embeddings_repo: EmbeddingsDBRepository,
    ):
        self.graph_memory = graph_memory
        self.decision_repo = decision_repo
        self.graph_traversal = graph_traversal
        self.context_cache = context_cache
        self.embeddings_repo = embeddings_repo

    def calculate_token_budget(self, total_budget: int = 128000) -> Dict[str, int]:
        return TokenBudgetAllocator.calculate_allocation(total_budget)

    async def build_optimal_context(
        self,
        user_prompt: str,
        session_id: str,
        user_id: str,
        project_id: str,
        max_token_budget: int = 128000,
        max_context_tokens: int = 8000
    ) -> Dict[str, Any]:
        logger.info(f"Pipeline start: Building context for session={session_id}, project={project_id}")
        budget = self.calculate_token_budget(max_token_budget)
        intent = IntentAnalyzerService.analyze(user_prompt)
        quick_nodes = self.embeddings_repo.hybrid_search(user_prompt, project_id, top_k=5)
        cache_hit, candidate_nodes = self.context_cache.get_delta_context(user_prompt, session_id, quick_nodes)

        if cache_hit:
            logger.info(f"Context Cache HIT for session={session_id}. Using cached base + delta nodes.")
            selected_nodes = candidate_nodes
        else:
            logger.info(f"Context Cache MISS for session={session_id}. Running full BFS Graph Traversal pipeline.")
            start_node_ids = set(n["node_id"] for n in quick_nodes if "node_id" in n)
            for kw in intent.get("keywords", []):
                if len(kw) > 3:
                    conn = self.graph_memory.graph_repo.db.get_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id FROM graph_nodes WHERE project_id=? AND user_id=? AND (label LIKE ? OR attributes_json LIKE ?) LIMIT 5",
                        (project_id, user_id, f"%{kw}%", f"%{kw}%")
                    )
                    for r in cur.fetchall():
                        start_node_ids.add(r["id"])
            subgraph = self.graph_traversal.traverse_from_nodes(
                start_node_ids=list(start_node_ids),
                project_id=project_id,
                user_id=user_id,
                depth=2,
                depth_decay=0.7
            )
            traversed_nodes = subgraph.get("nodes", [])
            selected_nodes = MemoryRankingService.rank_nodes(traversed_nodes, user_prompt)

        decisions = self.decision_repo.get_decisions(project_id, user_id, limit=5)
        parts = []
        if decisions:
            dec_lines = [f"- [{d['topic']}]: {d['decision']} (Rationale: {d['rationale']})" for d in decisions]
            parts.append("### ARCHITECTURAL DECISION MEMORY:\n" + "\n".join(dec_lines))
        if selected_nodes:
            top_nodes = selected_nodes[:12]
            node_lines = [f"- [{n['node_type'].upper()}] {n['label']} (Rank: {n.get('final_score', 0):.2f})" for n in top_nodes]
            parts.append("### RELEVANT KNOWLEDGE GRAPH NODES:\n" + "\n".join(node_lines))

        compiled_context = "\n".join(parts)
        initial_tokens = TokenBudgetAllocator.estimate_tokens(compiled_context)

        # Provider-safe context trimming
        max_char_limit = max_context_tokens * 4
        if len(compiled_context) > max_char_limit:
            compiled_context = compiled_context[:max_char_limit] + "\n[...graph memory capped...]"
            trimmed_tokens = TokenBudgetAllocator.estimate_tokens(compiled_context)
            logger.info(f"Context trimmed from {initial_tokens} to {trimmed_tokens} tokens for max_context_tokens={max_context_tokens}")

        self.context_cache.update_cache(session_id, user_prompt, selected_nodes[:12])
        return {
            "session_id": session_id,
            "project_id": project_id,
            "cache_hit": cache_hit,
            "budget": budget,
            "compiled_memory_context": compiled_context,
            "nodes_count": len(selected_nodes[:12]),
            "decisions_count": len(decisions)
        }
