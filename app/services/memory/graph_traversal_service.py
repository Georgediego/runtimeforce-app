"""
Graph Traversal Service implementing Breadth-First Search (BFS) over SQLite Graph Edges.
"""
import logging
from collections import deque
from typing import List, Dict, Any, Optional, Set
from app.repository.graph_db_repository import GraphDBRepository

logger = logging.getLogger("runtimeforce.service.memory.graph_traversal")

DEFAULT_RELATIONS = ["DEPENDS_ON", "CALLS", "CONTAINS", "USES", "RESOLVED_BY", "MODIFIED"]

class GraphTraversalService:
    def __init__(self, graph_repo: GraphDBRepository):
        self.graph_repo = graph_repo

    def traverse_from_nodes(
        self,
        start_node_ids: List[str],
        project_id: str,
        user_id: str,
        depth: int = 2,
        relation_types: Optional[List[str]] = None,
        depth_decay: float = 0.7
    ) -> Dict[str, Any]:
        if not start_node_ids:
            return {"nodes": [], "edges": []}

        allowed_relations = set(relation_types) if relation_types else set(DEFAULT_RELATIONS)
        conn = self.graph_repo.db.get_connection()
        cur = conn.cursor()

        visited_nodes: Dict[str, float] = {}
        queue = deque([(nid, 0, 1.0) for nid in start_node_ids if nid])
        collected_edges: List[Dict[str, Any]] = []
        visited_edge_ids: Set[str] = set()

        while queue:
            current_id, current_depth, current_weight = queue.popleft()
            
            if current_id in visited_nodes:
                if current_weight > visited_nodes[current_id]:
                    visited_nodes[current_id] = current_weight
                else:
                    continue
            else:
                visited_nodes[current_id] = current_weight

            if current_depth >= depth:
                continue

            cur.execute(
                """
                SELECT id, source_id, target_id, relation_type, weight 
                FROM graph_edges 
                WHERE source_id = ? OR target_id = ?
                """,
                (current_id, current_id)
            )
            edges = [dict(r) for r in cur.fetchall()]

            for edge in edges:
                rel = edge.get("relation_type", "")
                if rel not in allowed_relations:
                    continue

                edge_id = edge.get("id")
                if edge_id and edge_id not in visited_edge_ids:
                    visited_edge_ids.add(edge_id)
                    collected_edges.append(edge)

                neighbor_id = edge["target_id"] if edge["source_id"] == current_id else edge["source_id"]
                edge_weight = float(edge.get("weight", 1.0))
                next_weight = current_weight * edge_weight * depth_decay

                if neighbor_id not in visited_nodes or next_weight > visited_nodes[neighbor_id]:
                    queue.append((neighbor_id, current_depth + 1, next_weight))

        # Retrieve full node attributes for traversed IDs
        traversed_node_ids = list(visited_nodes.keys())
        node_records: List[Dict[str, Any]] = []

        if traversed_node_ids:
            placeholders = ",".join("?" for _ in traversed_node_ids)
            cur.execute(
                f"SELECT * FROM graph_nodes WHERE id IN ({placeholders}) AND project_id = ? AND user_id = ?",
                (*traversed_node_ids, project_id, user_id)
            )
            for r in cur.fetchall():
                node_dict = dict(r)
                node_id = node_dict["id"]
                node_dict["traversal_weight"] = visited_nodes.get(node_id, 1.0)
                node_records.append(node_dict)

        node_records.sort(key=lambda n: n.get("traversal_weight", 0.0), reverse=True)
        return {"nodes": node_records, "edges": collected_edges}
