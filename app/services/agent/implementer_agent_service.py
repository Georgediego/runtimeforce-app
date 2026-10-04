"""
Implementer Agent Service - Code implementation specialist in ATM mode.
Responsible for writing code, generating tests, applying fixes, and file operations.
"""

import logging
from typing import Any, Dict, List, Optional
import json

from app.core.events.event_bus import EventBus
from app.core.interfaces.implementer_agent_interface import IImplementerAgentService

logger = logging.getLogger(__name__)


class ImplementerAgentService(IImplementerAgentService):
    """
    Implementer role in Autonomous Team Mode (ATM).
    
    Responsibilities:
    - Write implementation code based on specifications
    - Generate unit and integration tests
    - Apply code fixes from Architect/Engineer feedback
    - Execute file operations (read/write/modify)
    - Ensure code follows project standards and patterns
    - Implement features step-by-step according to plan
    """
    
    def __init__(
        self,
        llm_orchestrator: Any,
        context_builder: Any,
        tool_dispatcher: Any,
        event_bus: Optional[EventBus] = None
    ) -> None:
        self._orchestrator = llm_orchestrator
        self._context_builder = context_builder
        self._tool_dispatcher = tool_dispatcher
        self._event_bus = event_bus
        
        self._system_prompt = """You are the Implementer in an autonomous development team.
Your responsibilities:
1. Write clean, maintainable implementation code based on specifications
2. Generate comprehensive unit and integration tests
3. Apply code fixes based on Architect and Engineer feedback
4. Execute file operations (read, write, modify) accurately
5. Follow project coding standards, patterns, and conventions
6. Implement features step-by-step according to the provided plan
7. Ensure proper error handling and edge case coverage
8. Write self-documenting code with appropriate comments

Always focus on:
- Code correctness and functionality
- Readability and maintainability
- Test coverage
- Performance considerations
- Security best practices
- Adherence to the specification

Respond in structured JSON format when reporting progress."""

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
        logger.info(f"[ImplementerAgent] Implementing feature for project {project_id}")
        
        prompt = f"""
Feature specification:
{self._format_specification(specification)}

Generate implementation code:
1. Identify all files that need to be created or modified
2. Write complete, working code for each file
3. Include proper imports, error handling, and documentation
4. Follow existing project patterns and conventions
5. Ensure all requirements are met

For each file provide:
- filepath: Full path to the file
- action: CREATE, MODIFY, or DELETE
- content: Complete file content (for CREATE/MODIFY)
- explanation: Brief description of changes

Format response as JSON."""
        
        try:
            context = await self._context_builder.build_optimal_context(
                project_id=project_id,
                user_prompt=f"Implement feature: {specification.get('description', '')}"
            )
            
            response = await self._orchestrator.generate_with_context(
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                context=context,
                temperature=0.2
            )
            
            implementation_plan = self._parse_implementation_response(response)
            
            # Execute file operations
            execution_results = await self._execute_file_operations(
                implementation_plan.get("files", []),
                project_id
            )
            
            result = {
                "status": "COMPLETED",
                "files_modified": len(execution_results),
                "execution_results": execution_results,
                "implementation_plan": implementation_plan
            }
            
            if self._event_bus:
                await self._event_bus.publish("implementer.feature_implemented", {
                    "project_id": project_id,
                    "files_count": len(execution_results),
                    "status": result["status"]
                })
            
            return result
        except Exception as e:
            logger.error(f"[ImplementerAgent] Feature implementation failed: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "files_modified": 0,
                "execution_results": []
            }
    
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
        logger.info(f"[ImplementerAgent] Generating tests for {code_location}")
        
        prompt = f"""
Code to test ({code_location}):
{code_content[:3000]}  # Limit length

Generate comprehensive tests:
1. Identify all functions/methods/classes that need testing
2. Create unit tests for each function
3. Include edge cases and error conditions
4. Add integration tests if applicable
5. Follow project's existing test patterns

Provide:
- test_filepath: Path where tests should be saved
- test_framework: pytest, unittest, jest, etc.
- test_content: Complete test file content
- coverage_notes: What is covered by these tests

Format response as JSON."""
        
        try:
            context = await self._context_builder.build_optimal_context(
                project_id=project_id,
                user_prompt=f"Generate tests for {code_location}"
            )
            
            response = await self._orchestrator.generate_with_context(
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                context=context,
                temperature=0.2
            )
            
            test_plan = self._parse_test_response(response)
            
            # Write test file
            if "test_content" in test_plan:
                write_result = await self._tool_dispatcher.execute(
                    tool_name="write_workspace_file",
                    arguments={
                        "file_path": test_plan.get("test_filepath", "test_file.py"),
                        "content": test_plan["test_content"]
                    }
                )
                
                test_plan["write_success"] = write_result.get("success", False)
            
            return test_plan
        except Exception as e:
            logger.error(f"[ImplementerAgent] Test generation failed: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "test_content": ""
            }
    
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
        logger.info(f"[ImplementerAgent] Applying fix to {file_path}")
        
        prompt = f"""
File: {file_path}

Current content:
{current_content[:3000]}

Fix required:
{fix_description}

Apply the fix:
1. Identify exact locations needing changes
2. Provide corrected code
3. Explain what was changed and why
4. Ensure no regressions are introduced

Provide:
- fixed_content: Complete corrected file content
- changes_summary: List of specific changes made
- risk_assessment: LOW/MEDIUM/HIGH risk of regression

Format response as JSON."""
        
        try:
            response = await self._orchestrator.generate_async(
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            
            fix_result = self._parse_fix_response(response)
            
            # Write fixed content
            if "fixed_content" in fix_result:
                write_result = await self._tool_dispatcher.execute(
                    tool_name="write_workspace_file",
                    arguments={
                        "file_path": file_path,
                        "content": fix_result["fixed_content"]
                    }
                )
                
                fix_result["write_success"] = write_result.get("success", False)
                fix_result["status"] = "FIXED" if fix_result["write_success"] else "FAILED"
            else:
                fix_result["status"] = "FAILED"
            
            return fix_result
        except Exception as e:
            logger.error(f"[ImplementerAgent] Fix application failed: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "fixed_content": ""
            }
    
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
        logger.info(f"[ImplementerAgent] Refactoring {function_name} in {file_path}")
        
        # Read current file content
        read_result = await self._tool_dispatcher.execute(
            tool_name="read_workspace_file",
            arguments={"file_path": file_path}
        )
        
        if not read_result.get("success", False):
            return {
                "status": "FAILED",
                "error": "Could not read file",
                "refactored_content": ""
            }
        
        current_content = read_result.get("content", "")
        
        prompt = f"""
File: {file_path}
Function: {function_name}

Current content:
{current_content[:3000]}

Refactoring goal:
{refactoring_goal}

Refactor the function:
1. Improve code structure and readability
2. Maintain backward compatibility
3. Keep the same external behavior
4. Add or update docstrings
5. Optimize performance if possible

Provide:
- refactored_content: Complete updated file content
- improvements: List of specific improvements made
- compatibility_notes: Any compatibility considerations

Format response as JSON."""
        
        try:
            response = await self._orchestrator.generate_async(
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            
            refactor_result = self._parse_refactor_response(response)
            
            # Write refactored content
            if "refactored_content" in refactor_result:
                write_result = await self._tool_dispatcher.execute(
                    tool_name="write_workspace_file",
                    arguments={
                        "file_path": file_path,
                        "content": refactor_result["refactored_content"]
                    }
                )
                
                refactor_result["write_success"] = write_result.get("success", False)
                refactor_result["status"] = "REFACTORED" if refactor_result["write_success"] else "FAILED"
            else:
                refactor_result["status"] = "FAILED"
            
            return refactor_result
        except Exception as e:
            logger.error(f"[ImplementerAgent] Refactoring failed: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "refactored_content": ""
            }
    
    def _format_specification(self, spec: Dict[str, Any]) -> str:
        """Format specification dictionary as readable text."""
        lines = []
        lines.append(f"Description: {spec.get('description', 'N/A')}")
        lines.append(f"Requirements: {spec.get('requirements', [])}")
        lines.append(f"Constraints: {spec.get('constraints', [])}")
        lines.append(f"Steps: {spec.get('steps', [])}")
        return "\n".join(lines)
    
    async def _execute_file_operations(
        self,
        files: List[Dict[str, Any]],
        project_id: str
    ) -> List[Dict[str, Any]]:
        """Execute file creation/modification operations."""
        results = []
        
        for file_op in files:
            filepath = file_op.get("filepath", "")
            action = file_op.get("action", "CREATE")
            content = file_op.get("content", "")
            
            try:
                if action == "DELETE":
                    result = await self._tool_dispatcher.execute(
                        tool_name="delete_file",
                        arguments={"file_path": filepath}
                    )
                elif action in ["CREATE", "MODIFY"]:
                    result = await self._tool_dispatcher.execute(
                        tool_name="write_workspace_file",
                        arguments={
                            "file_path": filepath,
                            "content": content
                        }
                    )
                else:
                    result = {"success": False, "error": f"Unknown action: {action}"}
                
                results.append({
                    "filepath": filepath,
                    "action": action,
                    "success": result.get("success", False),
                    "result": result
                })
                
            except Exception as e:
                results.append({
                    "filepath": filepath,
                    "action": action,
                    "success": False,
                    "error": str(e)
                })
        
        return results
    
    def _parse_implementation_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into implementation plan."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[ImplementerAgent] Failed to parse implementation response: {e}")
        
        return {
            "files": [],
            "error": "Failed to parse implementation plan"
        }
    
    def _parse_test_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into test plan."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[ImplementerAgent] Failed to parse test response: {e}")
        
        return {
            "test_filepath": "",
            "test_content": "",
            "error": "Failed to parse test plan"
        }
    
    def _parse_fix_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into fix result."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[ImplementerAgent] Failed to parse fix response: {e}")
        
        return {
            "fixed_content": "",
            "changes_summary": [],
            "risk_assessment": "UNKNOWN"
        }
    
    def _parse_refactor_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into refactor result."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[ImplementerAgent] Failed to parse refactor response: {e}")
        
        return {
            "refactored_content": "",
            "improvements": [],
            "compatibility_notes": ""
        }
