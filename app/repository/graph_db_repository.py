"""
Isolated SQLite Repository for Knowledge Graph Nodes, Edges, and Subgraph Traversal.
"""
import json
import logging
import time
from typing import Optional, Dict, Any, List
from app.repository.db_connection import DatabaseConnectionManager
from app.core.interfaces.graph_memory_interface import IGraphMemory

logger = logging.getLogger("runtimeforce.repository.graph")

SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    label TEXT NOT NULL,
    attributes_json TEXT,
    score_relevance REAL DEFAULT 1.0,
    score_importance REAL DEFAULT 1.0,
    usage_count INTEGER DEFAULT 1,
    last_used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS graph_edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES graph_nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES graph_nodes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_nodes_project ON graph_nodes(project_id, user_id);
CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target_id);
"""


class GraphDBRepository(IGraphMemory):
    def __init__(self, db_manager: DatabaseConnectionManager):
        self.db = db_manager
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        conn.executescript(SCHEMA)
        conn.commit()

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
        attr_str = json.dumps(attributes, ensure_ascii=False) if attributes else "{}"
        try:
            conn = self.db.get_connection()
            conn.execute(
                """
                INSERT INTO graph_nodes (id, user_id, project_id, node_type, label, attributes_json, score_importance)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    label=excluded.label,
                    attributes_json=excluded.attributes_json,
                    score_importance=excluded.score_importance,
                    usage_count=usage_count + 1,
                    last_used_at=CURRENT_TIMESTAMP
                """,
                (node_id, user_id, project_id, node_type, label, attr_str, importance)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add graph node {node_id}: {e}")
            return False

    def delete_session_memory(self, session_id: str, user_id: str, project_id: str = "") -> int:
        """Delete graph nodes and vectors explicitly attributed to this session only."""
        conn = self.db.get_connection()
        rows = conn.execute(
            "SELECT id, attributes_json FROM graph_nodes WHERE user_id=? AND (?='' OR project_id=?)",
            (user_id, project_id, project_id)
        ).fetchall()
        node_ids = []
        summary_prefix = f"summary-{session_id}-"
        for row in rows:
            try:
                attributes = json.loads(row["attributes_json"] or "{}")
            except (TypeError, ValueError):
                attributes = {}
            if attributes.get("session_id") == session_id or str(row["id"]).startswith(summary_prefix):
                node_ids.append(str(row["id"]))
        if not node_ids:
            return 0
        placeholders = ",".join("?" for _ in node_ids)
        conn.execute(
            f"DELETE FROM graph_edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
            [*node_ids, *node_ids],
        )
        conn.execute(f"DELETE FROM node_embeddings WHERE node_id IN ({placeholders})", node_ids)
        conn.execute(f"DELETE FROM graph_nodes WHERE id IN ({placeholders})", node_ids)
        conn.commit()
        return len(node_ids)

    def add_edge(
        self,
        edge_id: str,
        source_id: str,
        target_id: str,
        relation_type: str,
        weight: float = 1.0
    ) -> bool:
        try:
            conn = self.db.get_connection()
            scope = conn.execute(
                """
                SELECT source.project_id AS source_project, source.user_id AS source_user,
                       target.project_id AS target_project, target.user_id AS target_user
                FROM graph_nodes AS source
                JOIN graph_nodes AS target ON target.id=?
                WHERE source.id=?
                """,
                (target_id, source_id)
            ).fetchone()
            # Knowledge graph edges must never cross project or user boundaries.
            if (
                not scope
                or scope["source_project"] != scope["target_project"]
                or scope["source_user"] != scope["target_user"]
            ):
                logger.warning("Rejected cross-project or cross-user graph edge %s", edge_id)
                return False
            conn.execute(
                """
                INSERT INTO graph_edges (id, source_id, target_id, relation_type, weight)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET weight=excluded.weight
                """,
                (edge_id, source_id, target_id, relation_type, weight)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add edge {edge_id}: {e}")
            return False

    def query_subgraph(
        self,
        project_id: str,
        user_id: str,
        root_node_types: Optional[List[str]] = None,
        limit: int = 30
    ) -> Dict[str, Any]:
        conn = self.db.get_connection()
        cur = conn.cursor()

        if root_node_types:
            placeholders = ",".join("?" for _ in root_node_types)
            cur.execute(
                f"SELECT * FROM graph_nodes WHERE project_id=? AND user_id=? AND node_type IN ({placeholders}) ORDER BY usage_count DESC, last_used_at DESC LIMIT ?",
                (project_id, user_id, *root_node_types, limit)
            )
        else:
            cur.execute(
                "SELECT * FROM graph_nodes WHERE project_id=? AND user_id=? ORDER BY usage_count DESC, last_used_at DESC LIMIT ?",
                (project_id, user_id, limit)
            )

        nodes = [dict(r) for r in cur.fetchall()]
        node_ids = [n["id"] for n in nodes]
        edges = []

        if node_ids:
            placeholders = ",".join("?" for _ in node_ids)
            cur.execute(
                f"""
                SELECT edge.*
                FROM graph_edges AS edge
                JOIN graph_nodes AS source ON source.id=edge.source_id
                JOIN graph_nodes AS target ON target.id=edge.target_id
                WHERE source.project_id=? AND source.user_id=?
                  AND target.project_id=? AND target.user_id=?
                  AND (edge.source_id IN ({placeholders}) OR edge.target_id IN ({placeholders}))
                """,
                (project_id, user_id, project_id, user_id, *node_ids, *node_ids)
            )
            edges = [dict(r) for r in cur.fetchall()]

        return {"nodes": nodes, "edges": edges}

    def rank_nodes(self, nodes: List[Dict[str, Any]], query_text: str) -> List[Dict[str, Any]]:
        query_words = set(query_text.lower().split())

        for n in nodes:
            label = str(n.get("label", "")).lower()
            node_type = str(n.get("node_type", "")).lower()
            relevance = sum(2.0 for w in query_words if w in label or w in node_type)
            importance = float(n.get("score_importance", 1.0))
            usage = int(n.get("usage_count", 1))
            # Final Rank = Relevance * 0.4 + Importance * 0.3 + Usage * 0.3
            n["computed_rank"] = (relevance * 0.4) + (importance * 0.3) + (usage * 0.3)

        nodes.sort(key=lambda x: x.get("computed_rank", 0.0), reverse=True)
        return nodes

    async def get_graph_nodes_by_properties(
        self,
        properties: Dict[str, Any],
        label: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search graph nodes by attributes_json properties and optional node_type."""
        conn = self.db.get_connection()
        cur = conn.cursor()

        query = "SELECT * FROM graph_nodes WHERE 1=1"
        params: list = []

        if label:
            query += " AND node_type = ?"
            params.append(label)

        cur.execute(query, params)
        rows = cur.fetchall()

        results = []
        for row in rows:
            node = dict(row)
            try:
                attrs = json.loads(node.get("attributes_json") or "{}")
            except Exception:
                attrs = {}

            match = True
            for key, value in properties.items():
                if key == "project_id":
                    if node.get("project_id") != value:
                        match = False
                        break
                elif key == "user_id":
                    if node.get("user_id") != value:
                        match = False
                        break
                else:
                    if attrs.get(key) != value:
                        match = False
                        break

            if match:
                results.append(node)

        return results
