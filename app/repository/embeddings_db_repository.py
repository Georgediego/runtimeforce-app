import json
import logging
from typing import Dict, Any, List
from app.repository.db_connection import DatabaseConnectionManager
from app.core.interfaces.embedding_search_interface import IEmbeddingSearch
from app.core.interfaces.embedding_engine_interface import IEmbeddingEngine

logger = logging.getLogger("runtimeforce.repository.embeddings")

SCHEMA = """
CREATE TABLE IF NOT EXISTS node_embeddings (
    node_id TEXT PRIMARY KEY,
    text_content TEXT NOT NULL,
    vector_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

class EmbeddingsDBRepository(IEmbeddingSearch):
    def __init__(self, db_manager: DatabaseConnectionManager, embedding_engine: IEmbeddingEngine):
        self.db = db_manager
        self.embedding_engine = embedding_engine
        self.init_schema()

    def init_schema(self):
        conn = self.db.get_connection()
        conn.executescript(SCHEMA)
        conn.commit()

    def index_text(self, node_id: str, text_content: str) -> bool:
        try:
            vec = self.embedding_engine.get_embedding(text_content)
            vec_str = json.dumps(vec)

            conn = self.db.get_connection()
            conn.execute(
                """
                INSERT INTO node_embeddings (node_id, text_content, vector_json)
                VALUES (?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET 
                    text_content=excluded.text_content,
                    vector_json=excluded.vector_json
                """,
                (node_id, text_content[:5000], vec_str)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to index text for node {node_id}: {e}")
            return False

    def hybrid_search(self, query: str, project_id: str, top_k: int = 10) -> List[Dict[str, Any]]:
        query_vec = self.embedding_engine.get_embedding(query)
        conn = self.db.get_connection()
        cur = conn.cursor()
        
        keyword_term = f"%{query[:50]}%"
        cur.execute(
            """
            SELECT ne.node_id, gn.label, gn.node_type, gn.attributes_json
            FROM node_embeddings ne
            JOIN graph_nodes gn ON gn.id = ne.node_id
            WHERE gn.project_id = ? AND (gn.label LIKE ? OR ne.text_content LIKE ?)
            LIMIT ?
            """,
            (project_id, keyword_term, keyword_term, top_k)
        )
        keyword_results = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT ne.node_id, ne.vector_json, gn.label, gn.node_type 
            FROM node_embeddings ne
            JOIN graph_nodes gn ON gn.id = ne.node_id
            WHERE gn.project_id = ?
            """,
            (project_id,)
        )
        
        scored = []
        for row in cur.fetchall():
            vec_json = row["vector_json"]
            if vec_json:
                try:
                    stored_vec = json.loads(vec_json)
                    if len(stored_vec) == len(query_vec):
                        dot = sum(a * b for a, b in zip(query_vec, stored_vec))
                        scored.append({
                            "node_id": row["node_id"],
                            "label": row["label"],
                            "node_type": row["node_type"],
                            "score": dot
                        })
                except Exception:
                    pass

        scored.sort(key=lambda x: x["score"], reverse=True)
        vector_results = scored[:top_k]

        seen = set()
        merged = []
        for r in vector_results + keyword_results:
            nid = r["node_id"]
            if nid not in seen:
                seen.add(nid)
                merged.append(r)

        return merged[:top_k]
