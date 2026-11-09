"""
Builds the project memory context and records a compact trace of real SQLite operations.
"""
import logging
import time
from typing import Dict, Any, List
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
        trace: List[Dict[str, Any]] = []
        pipeline_started = time.perf_counter()

        def record(operation: str, label: str, detail: str, started: float, **extra: Any) -> None:
            item = {
                "operation": operation,
                "label": label,
                "detail": detail,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }
            item.update(extra)
            trace.append(item)

        logger.info(f"Pipeline start: Building context for session={session_id}, project={project_id}")
        budget = self.calculate_token_budget(max_token_budget)

        stage_started = time.perf_counter()
        intent = IntentAnalyzerService.analyze(user_prompt)
        record("intent", "Intent analysis", f"{len(intent.get('keywords', []))} search terms extracted", stage_started)

        stage_started = time.perf_counter()
        quick_nodes = self.embeddings_repo.hybrid_search(user_prompt, project_id, top_k=5)
        record(
            "hybrid_search", "Hybrid memory search",
            f"{len(quick_nodes)} candidate nodes · SQLite/vector index",
            stage_started, candidate_count=len(quick_nodes),
        )

        stage_started = time.perf_counter()
        cache_hit, candidate_nodes = self.context_cache.get_delta_context(user_prompt, session_id, quick_nodes)
        record(
            "context_cache", "Context cache " + ("HIT" if cache_hit else "MISS"),
            f"{len(candidate_nodes)} cached/delta nodes reused" if cache_hit else "Full graph traversal required",
            stage_started, cache_hit=bool(cache_hit), candidate_count=len(candidate_nodes),
        )

        traversal_node_count = 0
        traversal_edge_count = 0
        if cache_hit:
            logger.info(f"Context Cache HIT for session={session_id}. Using cached base + delta nodes.")
            selected_nodes = candidate_nodes
            trace.append({
                "operation": "graph_traversal_skipped",
                "label": "Graph traversal skipped",
                "detail": "Cache supplied the context; BFS was not needed",
                "duration_ms": 0,
            })
        else:
            logger.info(f"Context Cache MISS for session={session_id}. Running full BFS Graph Traversal pipeline.")
            stage_started = time.perf_counter()
            start_node_ids = set(n["node_id"] for n in quick_nodes if "node_id" in n)
            keyword_matches = 0
            for kw in intent.get("keywords", []):
                if len(kw) > 3:
                    conn = self.graph_memory.graph_repo.db.get_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id FROM graph_nodes WHERE project_id=? AND user_id=? AND (label LIKE ? OR attributes_json LIKE ?) LIMIT 5",
                        (project_id, user_id, f"%{kw}%", f"%{kw}%")
                    )
                    rows = cur.fetchall()
                    keyword_matches += len(rows)
                    for row in rows:
                        start_node_ids.add(row["id"])

            subgraph = self.graph_traversal.traverse_from_nodes(
                start_node_ids=list(start_node_ids),
                project_id=project_id,
                user_id=user_id,
                depth=2,
                depth_decay=0.7
            )
            traversed_nodes = subgraph.get("nodes", [])
            traversed_edges = subgraph.get("edges", [])
            traversal_node_count = len(traversed_nodes)
            traversal_edge_count = len(traversed_edges)
            selected_nodes = MemoryRankingService.rank_nodes(traversed_nodes, user_prompt)
            record(
                "graph_traversal", "SQLite graph traversal (BFS)",
                f"{len(start_node_ids)} seeds · {traversal_node_count} nodes · {traversal_edge_count} edges",
                stage_started, seed_count=len(start_node_ids), matched_keywords=keyword_matches,
                node_count=traversal_node_count, edge_count=traversal_edge_count,
            )

        stage_started = time.perf_counter()
        decisions = self.decision_repo.get_decisions(project_id, user_id, limit=5)
        record(
            "decision_lookup", "Decision memory lookup",
            f"{len(decisions)} project decisions loaded",
            stage_started, decision_count=len(decisions),
        )

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
        max_char_limit = max_context_tokens * 4
        if len(compiled_context) > max_char_limit:
            compiled_context = compiled_context[:max_char_limit] + "\n[...graph memory capped...]"
            trimmed_tokens = TokenBudgetAllocator.estimate_tokens(compiled_context)
            logger.info(f"Context trimmed from {initial_tokens} to {trimmed_tokens} tokens for max_context_tokens={max_context_tokens}")

        self.context_cache.update_cache(session_id, user_prompt, selected_nodes[:12])
        active_node_ids = [str(node.get("id")) for node in selected_nodes[:12] if node.get("id")]
        record(
            "context_ready", "Memory context assembled",
            f"{len(active_node_ids)} nodes selected · {initial_tokens} estimated tokens",
            pipeline_started, active_node_ids=active_node_ids,
        )
        return {
            "session_id": session_id,
            "project_id": project_id,
            "cache_hit": cache_hit,
            "budget": budget,
            "compiled_memory_context": compiled_context,
            "nodes_count": len(active_node_ids),
            "active_node_ids": active_node_ids,
            "decisions_count": len(decisions),
            "trace": trace,
            "graph_stats": {
                "candidate_nodes": len(quick_nodes),
                "traversed_nodes": traversal_node_count,
                "traversed_edges": traversal_edge_count,
                "selected_nodes": len(active_node_ids),
                "decisions": len(decisions),
                "context_tokens": initial_tokens,
            },
        }
