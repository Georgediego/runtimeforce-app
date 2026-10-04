from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IArchitectAgentService(ABC):
    """
    Interface for Architect Agent Service in ATM mode.
    Responsible for task decomposition, planning, code review, and DoD validation.
    """
    
    @abstractmethod
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
            override_model: Specific model to use (or "auto" for auto-selection)
            
        Returns:
            Dictionary with recommendation, model_id, and plan
        """
        pass
    
    @abstractmethod
    async def decompose_task(
        self,
        task_description: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Decompose a complex task into smaller, manageable steps.
        
        Args:
            task_description: The high-level task to decompose
            context: Project context, existing code, constraints
            
        Returns:
            Dictionary with decomposed steps and execution plan
        """
        pass
    
    @abstractmethod
    async def review_code(
        self,
        code_changes: Dict[str, str],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform code review on proposed changes.
        
        Args:
            code_changes: Dictionary of filepath -> diff/content
            context: Related requirements, standards
            
        Returns:
            Review results with approval status and feedback
        """
        pass
    
    @abstractmethod
    async def validate_dod(
        self,
        task_description: str,
        deliverables: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate Definition of Done for a task.
        
        Args:
            task_description: Original task description
            deliverables: What was delivered (code, tests, docs, etc.)
            
        Returns:
            Validation result with pass/fail status
        """
        pass
