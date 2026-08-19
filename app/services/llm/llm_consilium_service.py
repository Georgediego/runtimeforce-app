"""
Service for orchestrating 3-step Consilium debate with Multi-Axis Review (Draft -> Multi-Axis Audit -> Synthesis).
Guarantees full 3-step execution ending always with Synth.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger("runtimeforce.service.llm.consilium")

class LLMConsiliumService:
    @staticmethod
    def prepare_audit_prompt(user_query: str, draft_response: str) -> str:
        return (
            "You are a Lead Code Reviewer and Security Auditor in RuntimeForce AI Consilium.\n\n"
            "TASK: Perform a Strict Multi-Axis Review (/code-review) of the proposed draft solution.\n\n"
            "EVALUATION AXES:\n"
            "1. AXIS 1 (Syntax & Type Correctness): Check for syntax errors, invalid imports, type mismatches, and edge-case exceptions.\n"
            "2. AXIS 2 (Security & Performance): Identify memory/CPU leaks, unhandled async exceptions, injection risks, and performance bottlenecks.\n"
            "3. AXIS 3 (Spec & Requirement Compliance): Verify if the solution strictly fulfills ALL user requirements without missing features or hallucinating non-existent APIs.\n\n"
            "OUTPUT FORMAT:\n"
            "- List specific defects grouped by Axis.\n"
            "- Provide the exact corrected code block addressing all defects.\n"
            "- NO filler, no conversational preamble.\n\n"
            f"USER REQUEST:\n{user_query}\n\n"
            f"PROPOSED DRAFT SOLUTION:\n{draft_response}"
        )

    @staticmethod
    def prepare_synthesis_prompt(user_query: str, draft_response: str, critique_response: str) -> str:
        return (
            "You are the Lead System Architect in RuntimeForce AI Consilium.\n\n"
            "TASK:\n"
            "Merge the Draft solution and the Multi-Axis Critique into a single, flawless, production-ready answer.\n\n"
            "DIRECTIVES:\n"
            "- Resolve all defects raised in Axis 1 (Syntax), Axis 2 (Security/Perf), and Axis 3 (Spec Compliance).\n"
            "- Eliminate filler, fluff, and repetition loops.\n"
            "- Provide the final authoritative code and step-by-step instructions in the User's language.\n\n"
            f"USER REQUEST:\n{user_query}\n\n"
            f"DRAFT SOLUTION:\n{draft_response}\n\n"
            f"CRITIQUE & REVIEWS:\n{critique_response}"
        )
