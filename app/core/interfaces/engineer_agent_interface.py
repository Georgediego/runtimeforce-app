from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IEngineerAgentService(ABC):
    """
    Interface for Engineer Agent Service in ATM mode.
    Responsible for environment setup, test execution, error analysis, and refactoring.
    """
    
    @abstractmethod
    async def setup_environment(
        self,
        project_id: str,
        requirements: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Setup development environment for the project.
        
        Args:
            project_id: Project identifier
            requirements: Environment requirements (dependencies, tools, configs)
            
        Returns:
            Setup status and any issues encountered
        """
        pass
    
    @abstractmethod
    async def execute_tests(
        self,
        test_command: str,
        project_id: str
    ) -> Dict[str, Any]:
        """
        Execute tests and analyze results.
        
        Args:
            test_command: Test execution command (e.g., pytest, npm test)
            project_id: Project identifier
            
        Returns:
            Test results with pass/fail status and detailed output
        """
        pass
    
    @abstractmethod
    async def analyze_error(
        self,
        error_output: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze error output and identify root cause.
        
        Args:
            error_output: Error message or stack trace
            context: Related code, recent changes, environment info
            
        Returns:
            Error analysis with root cause hypothesis and suggested fixes
        """
        pass
    
    @abstractmethod
    async def refactor_code(
        self,
        feedback: Dict[str, Any],
        code_location: str
    ) -> Dict[str, Any]:
        """
        Refactor code based on Architect feedback.
        
        Args:
            feedback: Code review feedback from Architect
            code_location: File path or code section to refactor
            
        Returns:
            Refactoring plan and changes to apply
        """
        pass
    
    @abstractmethod
    async def prepare_context_for_implementer(
        self,
        task_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Prepare detailed context and specifications for Implementer.
        
        Args:
            task_spec: Task specification from Architect
            
        Returns:
            Prepared context with clear implementation instructions
        """
        pass
    
    @abstractmethod
    async def validate_tool_execution(
        self,
        tool_name: str,
        result: Dict[str, Any]
    ) -> bool:
        """
        Validate that a tool execution completed successfully.
        
        Args:
            tool_name: Name of the executed tool
            result: Tool execution result
            
        Returns:
            True if execution was successful, False otherwise
        """
        pass
