"""
HTTP API Router for inspecting Graph Memory, Decisions, and Token Budget.
"""
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends
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
    user_id: str = Depends(require_authenticated_user),
    graph_service: GraphMemoryService = Depends(get_graph_memory_service)
):
    """Return a compact, user/project-scoped graph snapshot for the local memory visualizer."""
    graph = graph_service.graph_repo.query_subgraph(project_id, user_id, limit=300)
    nodes = [
        {"id": str(node.get("id", "")), "label": str(node.get("label", "")), "type": str(node.get("node_type", "memory"))}
        for node in graph.get("nodes", [])
        if node.get("id")
    ]
    node_ids = {node["id"] for node in nodes}
    edges = [
        {"source": str(edge.get("source_id", "")), "target": str(edge.get("target_id", ""))}
        for edge in graph.get("edges", [])
        if str(edge.get("source_id", "")) in node_ids and str(edge.get("target_id", "")) in node_ids
    ][:900]
    return {"project_id": project_id, "nodes": nodes, "edges": edges}


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
