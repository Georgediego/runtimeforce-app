"""
Architect Agent Service - Responsible for task decomposition, planning, 
code review, and Definition of Done (DoD) control in ATM mode.
"""

import logging
from typing import Any, Dict, List, Optional
import json

from app.core.events.event_bus import EventBus
from app.core.interfaces.architect_agent_interface import IArchitectAgentService

logger = logging.getLogger(__name__)


class ArchitectAgentService(IArchitectAgentService):
    """
    Architect role in Autonomous Team Mode (ATM).
    
    Responsibilities:
    - Decompose complex tasks into smaller, manageable steps
    - Create detailed execution plans with role assignments
    - Perform code reviews for quality and architecture compliance
    - Define and validate Definition of Done (DoD) criteria
    - Make final decisions on task completion or request revisions
    - Ensure architectural consistency and design patterns
    """
    
    def __init__(
        self,
        llm_orchestrator: Any,
        context_builder: Any,
        event_bus: Optional[EventBus] = None
    ) -> None:
        self._orchestrator = llm_orchestrator
        self._context_builder = context_builder
        self._event_bus = event_bus
        
        self._system_prompt = """You are the Architect in an autonomous development team.
Your responsibilities:
1. Analyze requirements and decompose them into clear, actionable steps
2. Create detailed execution plans with milestones
3. Review code changes for quality, architecture compliance, and best practices
4. Define and validate Definition of Done (DoD) criteria
5. Make final decisions on task completion or request revisions
6. Ensure architectural consistency and design patterns are followed

Always think systematically and consider:
- Code maintainability and scalability
- Separation of concerns
- Test coverage requirements
- Error handling and edge cases
- Performance implications

Respond in structured JSON format when creating plans."""

    async def consult(
        self,
        user_prompt: str,
        project_id: str,
        user_id: str,
        user_plan: str,
        enabled_models: Optional[List[str]] = None,
        override_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate authoritative action plan for ATM execution.
        
        Args:
            user_prompt: Original user request
            project_id: Project identifier
            user_id: User identifier
            user_plan: User-provided plan or context
            enabled_models: List of enabled model IDs
            override_model: Specific model to use
            
        Returns:
            Dictionary with recommendation and model info
        """
        logger.info(
            f"[ArchitectAgent] Generating action plan for project {project_id}, plan={user_plan}"
        )

        # Use override model or default to auto-selection by orchestrator
        model_id = override_model if override_model and override_model != "auto" else "auto"

        # Build context for architectural decision
        context = await self._context_builder.build_optimal_context(
            project_id=project_id,
            user_prompt=user_prompt
        )
        
        # Decompose task if no user plan provided
        if not user_plan:
            decomposition = await self.decompose_task(user_prompt, context)
            user_plan = decomposition.get("plan", "")

        recommendation = (
            "EXECUTION PLAN:\n"
            "1. Tool `read_workspace_file` / `search_grep`: Inspect target files and locate requirements.\n"
            "2. Tool `write_workspace_file`: Write or update implementation code directly to disk.\n"
            "3. Tool `execute_command`: Run tests or environment validation commands to verify correctness.\n"
            "4. Tool `git_status` / `git_commit`: Verify changed files and finalize task."
        )

        if self._event_bus:
            await self._event_bus.publish("architect.consulted", {
                "project_id": project_id,
                "model_used": model_id,
                "plan_generatedERATION": user_plan[:200]  # First 200 chars for logging
            })

        return {"recommendation": recommendation, "model_id": model_id, "plan": user_plan}
    
    async def decompose_task(self, task_description: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decompose a complex task into smaller, manageable steps.
        
        Args:
            task_description: The high-level task to decompose
            context: Project context, existing code, constraints
            
        Returns:
            Dictionary with decomposed steps and plan
        """
        prompt = f"""
Task: {task_description}

Context:
{self._format_context(context)}

Break this task into clear, sequential steps. For each step specify:
- Step number and name
- Description of what needs to be done
- Expected output/deliverable
- Dependencies on previous steps
- Estimated complexity (low/medium/high)
- Assigned role (Architect/Engineer/Implementer/Designer)

Format response as JSON."""
        
        try:
            response = await self._orchestrator.generate_with_context(
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                context=context,
                temperature=0.3
            )
            
            return self._parse_plan_response(response)
        except Exception as e:
            logger.error(f"[ArchitectAgent] Task decomposition failed: {e}")
            return {
                "steps": [],
                "plan": f"Decomposition failed: {str(e)}",
                "error": str(e)
            }
    
    async def review_code(self, code_changes: Dict[str, str], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform code review on proposed changes.
        
        Args:
            code_changes: Dictionary of filepath -> diff/content
            context: Related requirements, standards
            
        Returns:
            Review results with approval status and feedback
        """
        prompt = f"""
Review the following code changes:

{self._format_code_changes(code_changes)}

Context and requirements:
{self._format_context(context)}

Evaluate based on:
1. Code quality and readability
2. Architecture compliance
3. Test coverage
4. Error handling
5. Performance
6. Security considerations
7. Adherence to Definition of Done

Provide:
- overall_assessment: APPROVE or REQUEST_CHANGES
- issues: list of specific issues found
- suggestions: list of improvement suggestions
- blocking_issues: list of critical blocking issues

Format response as JSON."""
        
        try:
            response = await self._orchestrator.generate_with_context(
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                context=context,
                temperature=0.2
            )
            
            return self._parse_review_response(response)
        except Exception as e:
            logger.error(f"[ArchitectAgent] Code review failed: {e}")
            return {
                "overall_assessment": "REQUEST_CHANGES",
                "issues": [f"Review failed: {str(e)}"],
                "suggestions": [],
                "blocking_issues": []
            }
    
    async def validate_dod(self, task_description: str, deliverables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate Definition of Done for a task.
        
        Args:
            task_description: Original task description
            deliverables: What was delivered (code, tests, docs, etc.)
            
        Returns:
            Validation result with pass/fail status
        """
        prompt = f"""
Task: {task_description}

Deliverables:
{self._format_deliverables(deliverables)}

Check if Definition of Done is met:
- All requirements implemented
- Tests written and passing
- Code reviewed and approved
- Documentation updated (if needed)
- No breaking changes (or properly versioned)
- Error handling implemented
- Edge cases covered

Respond with:
- dod_satisfied: boolean
- missing_items: list of unmet criteria
- comments: additional feedback

Format as JSON."""
        
        try:
            response = await self._orchestrator.generate_with_context(
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                context={},
                temperature=0.2
            )
            
            return self._parse_dod_response(response)
        except Exception as e:
            logger.error(f"[ArchitectAgent] DoD validation failed: {e}")
            return {
                "dod_satisfied": False,
                "missing_items": [f"Validation failed: {str(e)}"],
                "comments": ""
            }
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context dictionary as readable text."""
        if not context:
            return "No additional context provided."
        
        lines = []
        for key, value in context.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)
    
    def _format_code_changes(self, code_changes: Dict[str, str]) -> str:
        """Format code changes as readable text."""
        lines = []
        for filepath, content in code_changes.items():
            lines.append(f"\n--- {filepath} ---\n{content[:500]}")  # Limit content length
        return "\n".join(lines)
    
    def _format_deliverables(self, deliverables: Dict[str, Any]) -> str:
        """Format deliverables as readable text."""
        lines = []
        for key, value in deliverables.items():
            lines.append(f"- {key}: {str(value)[:200]}")
        return "\n".join(lines)
    
    def _parse_plan_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into plan structure."""
        try:
            # Extract JSON from response
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[ArchitectAgent] Failed to parse plan response: {e}")
        
        return {
            "steps": [],
            "plan": response[:500],  # Truncate for safety
            "error": "Failed to parse plan response"
        }
    
    def _parse_review_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into review structure."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[ArchitectAgent] Failed to parse review response: {e}")
        
        return {
            "overall_assessment": "REQUEST_CHANGES",
            "issues": ["Failed to parse review"],
            "suggestions": [],
            "blocking_issues": []
        }
    
    def _parse_dod_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into DoD validation structure."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[ArchitectAgent] Failed to parse DoD response: {e}")
        
        return {
            "dod_satisfied": False,
            "missing_items": ["Failed to parse validation"],
            "comments": ""
        }
