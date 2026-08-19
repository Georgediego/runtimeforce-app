"""
Summarizer Service for compressing long message chains into Graph Summary Nodes.
"""
import logging
from typing import List, Dict, Any, Optional
from app.services.memory.graph_memory_service import GraphMemoryService

logger = logging.getLogger("runtimeforce.service.memory.summarizer")

class SummarizerService:
    def __init__(self, graph_memory: GraphMemoryService):
        self.graph_memory = graph_memory

    async def compress_conversation(
        self,
        session_id: str,
        project_id: str,
        user_id: str,
        messages: List[Dict[str, Any]],
        orchestrator: Any
    ) -> Optional[Dict[str, Any]]:
        if len(messages) < 20:
            return None

        older = messages[:-5]
        formatted = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in older)

        prompt = [
            {
                "role": "system",
                "content": (
                    "Summarize this technical discussion into 3 bullet points of key decisions, "
                    "code modifications, and user preferences. Be concise and precise."
                )
            },
            {"role": "user", "content": formatted[:3000]}
        ]

        summary_text = ""
        try:
            async for chunk in orchestrator.stream_completion(
                messages=prompt,
                strategy="auto",
                temperature=0.2,
                user_id=user_id
            ):
                if chunk.get("content"):
                    summary_text += chunk["content"]
        except Exception as e:
            logger.error(f"Conversation summarization failed: {e}")
            return None

        summary_node_id = f"summary-{session_id}-{len(older)}"
        self.graph_memory.record_entity(
            node_id=summary_node_id,
            user_id=user_id,
            project_id=project_id,
            node_type="Summary",
            label=f"Summary of {len(older)} messages",
            attributes={"session_id": session_id, "summary": summary_text},
            text_for_search=summary_text
        )

        return {"summary_node_id": summary_node_id, "summary_text": summary_text}
