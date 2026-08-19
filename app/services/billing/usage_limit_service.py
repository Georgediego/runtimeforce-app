"""
Service for checking operation cost limits per plan tier.
"""
import logging

logger = logging.getLogger("runtimeforce.service.billing.usage")

PLAN_MAX_OPERATION_COST = {
    "free": 0,
    "pro": 500,
    "studio": 2000,
}

class UsageLimitService:
    @staticmethod
    def check_operation_limit(plan: str, estimated_cost: int) -> bool:
        max_allowed = PLAN_MAX_OPERATION_COST.get(plan.lower(), 0)
        return estimated_cost <= max_allowed
