"""
Service for recalculating dynamic smart scores for models based on telemetry metrics and provider degradation penalties.
"""
import logging
import time
from typing import Dict, Any, Optional
from app.repository.telemetry_db_repository import TelemetryDBRepository

logger = logging.getLogger("runtimeforce.service.llm.scoring")

class LLMScoringService:
    def __init__(self, telemetry_repo: TelemetryDBRepository, rotation_service: Optional[Any] = None):
        self.telemetry_repo = telemetry_repo
        self.rotation_service = rotation_service

    def get_scores(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        raw_scores = self.telemetry_repo.get_model_scores(user_id)
        
        if self.rotation_service:
            for model_id, data in raw_scores.items():
                provider = data.get("provider", "").lower()
                if self.rotation_service.is_provider_degraded(provider):
                    data["total"] = max(1.0, float(data.get("total", 50.0)) * 0.7)
                    data["degraded"] = True
                if not self.rotation_service.is_model_available(model_id):
                    data["total"] = max(1.0, float(data.get("total", 50.0)) * 0.5)

        return raw_scores

    def get_model_score(self, model_id: str, provider: str, user_id: str = "anonymous") -> float:
        scores = self.get_scores(user_id)
        model_data = scores.get(model_id, {})
        base_score = float(model_data.get("total", 50.0))
        return base_score
