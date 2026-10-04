"""
Structured Decision Recorder Service (v2) using Strict JSON Extraction and LLM Fallback.
"""
import json
import logging
from typing import List, Dict, Any, Optional
from app.repository.decision_db_repository import DecisionDBRepository
from app.services.memory.graph_memory_service import GraphMemoryService

logger = logging.getLogger("runtimeforce.service.memory.decision_recorder")

TRIGGER_KEYWORDS = ["decision", "architecture", "choice", "chosen", "решение", "архитектур"]

class DecisionRecorderService:
    def __init__(self, decision_repo: DecisionDBRepository, graph_memory: GraphMemoryService):
        self.decision_repo = decision_repo
        self.graph_memory = graph_memory

    async def extract_decisions_from_llm_response(
        self,
        llm_text: str,
        project_id: str,
        user_id: str,
        orchestrator: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        if not llm_text:
            return []

        # Step 1: Direct JSON parsing
        decisions = self._parse_json_from_text(llm_text)

        # Step 2: Fallback to LLM Structured Extraction if keywords present but JSON missing
        if not decisions and orchestrator and any(kw in llm_text.lower() for kw in TRIGGER_KEYWORDS):
            try:
                extraction_prompt = [
                    {
                        "role": "system",
                        "content": (
                            "You are a Decision Extraction AI. Inspect the provided technical text and extract "
                            "all explicit architectural/technical decisions made. Return ONLY a strict JSON array with format:\n"
                            '[{"topic": "...", "decision": "...", "rationale": "..."}]\n'
                            "If no decisions were made, return []."
                        )
                    },
                    {"role": "user", "content": llm_text[:2000]}
                ]
                acc = ""
                async for chunk in orchestrator.stream_completion(
                    messages=extraction_prompt,
                    strategy="auto",
                    temperature=0.1,
                    user_id=user_id
                ):
                    if chunk.get("content"):
                        acc += chunk["content"]

                decisions = self._parse_json_from_text(acc)
            except Exception as e:
                logger.debug(f"LLM decision extraction fallback failed: {e}")

        recorded = []
        for d in decisions:
            topic = str(d.get("topic", "Architecture")).strip()
            decision = str(d.get("decision", "")).strip()
            rationale = str(d.get("rationale", "")).strip()

            if topic and decision:
                rec = self.decision_repo.record_decision(project_id, user_id, topic, decision, rationale)
                if "id" in rec:
                    node_id = rec["id"]
                    self.graph_memory.record_entity(
                        node_id=node_id,
                        user_id=user_id,
                        project_id=project_id,
                        node_type="Decision",
                        label=f"Decision [{topic}]: {decision[:40]}",
                        attributes={"topic": topic, "decision": decision, "rationale": rationale},
                        text_for_search=f"{topic} {decision} {rationale}"
                    )
                    recorded.append(rec)

        return recorded

    @staticmethod
    def _parse_json_from_text(text: str) -> List[Dict[str, Any]]:
        try:
            if "```json" in text:
                text = text.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in text:
                text = text.split("```", 1)[1].split("```", 1)[0]

            data = json.loads(text.strip())
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
        except Exception:
            pass
        return []
