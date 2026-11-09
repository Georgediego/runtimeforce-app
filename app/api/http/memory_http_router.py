"""
HTTP API Router for inspecting Graph Memory, Decisions, and Token Budget.
"""
import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.security.jwt_auth_service import require_authenticated_user
from app.container import get_graph_memory_service, get_context_builder_service, get_decision_repo
from app.services.memory.graph_memory_service import GraphMemoryService
from app.services.memory.context_builder_service import ContextBuilderService
from app.repository.decision_db_repository import DecisionDBRepository

logger = logging.getLogger("runtimeforce.api.http.memory")
router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


class DecisionPayload(BaseModel):
    project_id: str
    topic: str
    decision: str
    rationale: str


@router.get("/subgraph/{project_id}")
async def get_subgraph(
    project_id: str,
    user_id: str = Depends(require_authenticated_user),
    graph_service: GraphMemoryService = Depends(get_graph_memory_service)
):
    subgraph = graph_service.get_working_memory_context(project_id, user_id)
    return {"project_id": project_id, "subgraph": subgraph}


@router.get("/graph-status/{project_id}")
async def get_graph_status(
    project_id: str,
    active_node_ids: Optional[List[str]] = Query(default=None),
    user_id: str = Depends(require_authenticated_user),
    graph_service: GraphMemoryService = Depends(get_graph_memory_service)
):
    """Return every real node and relationship stored for this project in SQLite."""
    conn = graph_service.graph_repo.db.get_connection()
    requested_ids = list(dict.fromkeys(str(value) for value in (active_node_ids or []) if value))[:30]

    # Return the complete project graph, not the small ranked subgraph used for prompt context.
    raw_nodes = conn.execute(
        """
        SELECT * FROM graph_nodes
        WHERE project_id=? AND user_id=?
        ORDER BY usage_count DESC, last_used_at DESC, created_at DESC
        """,
        (project_id, user_id),
    ).fetchall()
    raw_nodes = [dict(row) for row in raw_nodes]
    nodes = [
        {
            "id": str(node["id"]),
            "label": str(node.get("label") or ""),
            "type": str(node.get("node_type") or "memory"),
            "usage_count": int(node.get("usage_count") or 0),
        }
        for node in raw_nodes
        if node.get("id")
    ]
    node_ids = [node["id"] for node in nodes]
    edges = []
    if node_ids:
        # Both endpoints are scoped to this user/project; no giant IN clause
        # that would exceed SQLite's bind-variable limit on larger graphs.
        rows = conn.execute(
            """
            SELECT edge.id, edge.source_id, edge.target_id, edge.relation_type, edge.weight
            FROM graph_edges AS edge
            JOIN graph_nodes AS source ON source.id=edge.source_id
            JOIN graph_nodes AS target ON target.id=edge.target_id
            WHERE source.project_id=? AND source.user_id=?
              AND target.project_id=? AND target.user_id=?
            ORDER BY edge.weight DESC, edge.created_at DESC
            """,
            (project_id, user_id, project_id, user_id),
        ).fetchall()
        edges = [
            {
                "id": str(edge["id"]),
                "source": str(edge["source_id"]),
                "target": str(edge["target_id"]),
                "relation": str(edge["relation_type"] or "RELATED_TO"),
                "weight": float(edge["weight"] or 1.0),
            }
            for edge in rows
        ]

    total_nodes = conn.execute(
        "SELECT COUNT(*) FROM graph_nodes WHERE project_id=? AND user_id=?",
        (project_id, user_id),
    ).fetchone()[0]
    total_edges = conn.execute(
        """
        SELECT COUNT(*)
        FROM graph_edges AS edge
        JOIN graph_nodes AS source ON source.id=edge.source_id
        JOIN graph_nodes AS target ON target.id=edge.target_id
        WHERE source.project_id=? AND source.user_id=?
          AND target.project_id=? AND target.user_id=?
        """,
        (project_id, user_id, project_id, user_id),
    ).fetchone()[0]

    return {
        "project_id": project_id,
        "nodes": nodes,
        "edges": edges,
        "total_nodes": int(total_nodes),
        "total_edges": int(total_edges),
        "truncated": False,
        "active_node_ids": [node_id for node_id in requested_ids if node_id in {node["id"] for node in nodes}],
    }

@router.get("/decisions/{project_id}")
async def get_decisions(
    project_id: str,
    user_id: str = Depends(require_authenticated_user),
    decision_repo: DecisionDBRepository = Depends(get_decision_repo)
):
    decisions = decision_repo.get_decisions(project_id, user_id)
    return {"project_id": project_id, "decisions": decisions}


@router.post("/decisions")
async def record_decision(
    payload: DecisionPayload,
    user_id: str = Depends(require_authenticated_user),
    decision_repo: DecisionDBRepository = Depends(get_decision_repo)
):
    return decision_repo.record_decision(payload.project_id, user_id, payload.topic, payload.decision, payload.rationale)


@router.post("/context/preview")
async def preview_context(
    payload: Dict[str, Any],
    user_id: str = Depends(require_authenticated_user),
    builder: ContextBuilderService = Depends(get_context_builder_service)
):
    prompt = payload.get("prompt", "")
    session_id = payload.get("session_id", "preview")
    project_id = payload.get("project_id", "default")
    return await builder.build_optimal_context(prompt, session_id, user_id, project_id)
