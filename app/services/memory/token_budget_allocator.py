"""
Dynamic Token Budget Allocator for Capping LLM Prompt Context.
Proportionally scales token budgets based on target LLM max context size.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger("runtimeforce.service.memory.token_budget")


class TokenBudgetAllocator:
    @staticmethod
    def calculate_allocation(total_context_limit: int = 128000) -> Dict[str, int]:
        effective_limit = min(total_context_limit, 128000)
        
        return {
            "system_prompt": int(effective_limit * 0.08),
            "user_prompt": int(effective_limit * 0.05),
            "files": int(effective_limit * 0.25),
            "graph_memory": int(effective_limit * 0.15),
            "git": int(effective_limit * 0.10),
            "decisions": int(effective_limit * 0.07),
            "terminal": int(effective_limit * 0.05),
            "reserve": int(effective_limit * 0.25),
        }

    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return len(text) // 4

    @staticmethod
    def get_provider_safe_budget(provider: str) -> int:
        p = (provider or "").lower().strip()
        provider_limits = {
            "groq": 10000,
            "gemini": 25000,
            "openrouter": 15000,
            "cerebras": 15000,
            "sambanova": 10000,
        }
        return provider_limits.get(p, 8000)
