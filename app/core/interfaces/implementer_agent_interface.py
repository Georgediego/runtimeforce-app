from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IImplementerAgentService(ABC):
    """
    Interface for Implementer Agent Service in ATM mode.
    Responsible for writing code, generating tests, applying fixes, and file operations.
    """
    
    @abstractmethod
    async def implement_feature(
        self,
        specification: Dict[str, Any],
        project_id: str
    ) -> Dict[str, Any]:
        """
        Implement a feature based on detailed specification.
        
        Args:
            specification: Feature specification with requirements and steps
            project_id: Project identifier
            
        Returns:
            Implementation results with file changes and status
        """
        pass
    
    @abstractmethod
    async def generate_tests(
        self,
        code_location: str,
        code_content: str,
        project_id: str
    ) -> Dict[str, Any]:
        """
        Generate comprehensive tests for given code.
        
        Args:
            code_location: File path of the code to test
            code_content: Source code content
            project_id: Project identifier
            
        Returns:
            Generated tests with file location and coverage info
        """
        pass
    
    @abstractmethod
    async def apply_fix(
        self,
        fix_description: str,
        file_path: str,
        current_content: str,
        project_id: str
    ) -> Dict[str, Any]:
        """
        Apply a code fix based on feedback.
        
        Args:
            fix_description: Description of what needs to be fixed
            file_path: Path to the file needing fixes
            current_content: Current file content
            project_id: Project identifier
            
        Returns:
            Fixed code and change summary
        """
        pass
    
    @abstractmethod
    async def refactor_function(
        self,
        function_name: str,
        file_path: str,
        refactoring_goal: str,
        project_id: str
    ) -> Dict[str, Any]:
        """
        Refactor a specific function or method.
        
        Args:
            function_name: Name of function to refactor
            file_path: File containing the function
            refactoring_goal: What improvement is needed
            project_id: Project identifier
            
        Returns:
            Refactored code and improvement summary
        """
        pass
