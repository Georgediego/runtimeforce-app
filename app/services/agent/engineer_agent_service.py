"""
Engineer Agent Service - Bridging role in ATM mode.
Responsible for environment setup, test execution, error analysis, 
refactoring, and data preparation for Implementer and Designer.
"""

import logging
from typing import Any, Dict, List, Optional
import json

from app.core.events.event_bus import EventBus
from app.core.interfaces.engineer_agent_interface import IEngineerAgentService

logger = logging.getLogger(__name__)


class EngineerAgentService(IEngineerAgentService):
    """
    Engineer role in Autonomous Team Mode (ATM).
    
    Responsibilities:
    - Setup development environment and dependencies
    - Execute tests and analyze results
    - Debug errors and prepare diagnostic information
    - Refactor code based on Architect feedback
    - Prepare context and data for Implementer and Designer roles
    - Validate tool execution results
    - Bridge between planning and implementation
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
        
        self._system_prompt = """You are the Engineer in an autonomous development team.
Your responsibilities:
1. Setup development environment, install dependencies, configure tools
2. Execute tests and analyze test results thoroughly
3. Debug errors, run diagnostic commands, identify root causes
4. Refactor code based on Architect review feedback
5. Prepare context, documentation, and specifications for Implementer and Designer
6. Validate that tool executions completed successfully
7. Bridge between Architect's planning and Implementer's execution
8. Ensure code quality standards and best practices are followed

Always be methodical and thorough:
- Verify environment readiness before implementation starts
- Run comprehensive tests after changes
- Document findings clearly for the team
- Identify edge cases and potential issues
- Optimize for maintainability and performance

Respond in structured JSON format when reporting status."""

    async def setup_environment(self, project_id: str, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """
        Setup development environment for the project.
        
        Args:
            project_id: Project identifier
            requirements: Environment requirements (dependencies, tools, configs)
            
        Returns:
            Setup status and any issues encountered
        """
        logger.info(f"[EngineerAgent] Setting up environment for project {project_id}")
        
        prompt = f"""
Project requirements:
{self._format_requirements(requirements)}

Create a step-by-step environment setup plan:
1. Check existing environment state
2. Install missing dependencies
3. Configure tools and settings
4. Verify setup completion
5. Run initial validation tests

For each step specify:
- Command to execute
- Expected outcome
- Fallback if command fails
- Success criteria

Format response as JSON."""
        
        try:
            context = await self._context_builder.build_optimal_context(
                project_id=project_id,
                user_prompt="Setup development environment"
            )
            
            response = await self._orchestrator.generate_with_context(
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                context=context,
                temperature=0.3
            )
            
            result = self._parse_setup_response(response)
            
            # Execute setup steps via tools
            if "steps" in result:
                result["execution_log"] = await self._execute_setup_steps(
                    result["steps"],
                    project_id
                )
            
            return result
        except Exception as e:
            logger.error(f"[EngineerAgent] Environment setup failed: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "execution_log": []
            }
    
    async def execute_tests(self, test_command: str, project_id: str) -> Dict[str, Any]:
        """
        Execute tests and analyze results.
        
        Args:
            test_command: Test execution command (e.g., pytest, npm test)
            project_id: Project identifier
            
        Returns:
            Test results with pass/fail status and detailed output
        """
        logger.info(f"[EngineerAgent] Executing tests: {test_command}")
        
        try:
            # Execute test command via tool dispatcher
            result = await self._tool_dispatcher.execute(
                tool_name="execute_command",
                arguments={
                    "command": test_command,
                    "cwd": None,  # Will use project workspace
                    "timeout": 300  # 5 minutes max
                }
            )
            
            # Analyze test output
            analysis = await self._analyze_test_output(result.get("output", ""))
            
            test_result = {
                "status": "PASSED" if analysis.get("all_passed") else "FAILED",
                "exit_code": result.get("exit_code", -1),
                "output": result.get("output", ""),
                "total_tests": analysis.get("total_tests", 0),
                "passed_tests": analysis.get("passed_tests", 0),
                "failed_tests": analysis.get("failed_tests", 0),
                "failed_test_names": analysis.get("failed_test_names", []),
                "error_messages": analysis.get("error_messages", [])
            }
            
            if self._event_bus:
                await self._event_bus.publish("engineer.tests_completed", {
                    "project_id": project_id,
                    "status": test_result["status"],
                    "passed": test_result["passed_tests"],
                    "failed": test_result["failed_tests"]
                })
            
            return test_result
        except Exception as e:
            logger.error(f"[EngineerAgent] Test execution failed: {e}")
            return {
                "status": "ERROR",
                "exit_code": -1,
                "output": "",
                "error": str(e)
            }
    
    async def analyze_error(self, error_output: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze error output and identify root cause.
        
        Args:
            error_output: Error message or stack trace
            context: Related code, recent changes, environment info
            
        Returns:
            Error analysis with root cause hypothesis and suggested fixes
        """
        logger.info(f"[EngineerAgent] Analyzing error")
        
        prompt = f"""
Error output:
{error_output[:2000]}  # Limit length

Context:
{self._format_context(context)}

Analyze this error and provide:
1. Root cause hypothesis (what likely caused this)
2. Contributing factors (environment, dependencies, code issues)
3. Suggested fixes (prioritized list)
4. Commands to run for further diagnosis
5. Files likely needing changes

Be specific and actionable. Format response as JSON."""
        
        try:
            response = await self._orchestrator.generate_with_context(
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                context=context,
                temperature=0.2
            )
            
            return self._parse_error_analysis_response(response)
        except Exception as e:
            logger.error(f"[EngineerAgent] Error analysis failed: {e}")
            return {
                "root_cause": "Analysis failed",
                "hypothesis": [],
                "suggested_fixes": [],
                "diagnostic_commands": [],
                "files_to_change": []
            }
    
    async def refactor_code(self, feedback: Dict[str, Any], code_location: str) -> Dict[str, Any]:
        """
        Refactor code based on Architect feedback.
        
        Args:
            feedback: Code review feedback from Architect
            code_location: File path or code section to refactor
            
        Returns:
            Refactoring plan and changes to apply
        """
        logger.info(f"[EngineerAgent] Refactoring code at {code_location}")
        
        prompt = f"""
Architect feedback:
{self._format_feedback(feedback)}

Code location: {code_location}

Create a refactoring plan:
1. Identify specific code sections to change
2. Describe changes needed for each section
3. Ensure all feedback points are addressed
4. Maintain backward compatibility where possible
5. Add or update tests if needed

Format response as JSON with concrete changes."""
        
        try:
            response = await self._orchestrator.generate_with_context(
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                context={},
                temperature=0.3
            )
            
            return self._parse_refactor_response(response)
        except Exception as e:
            logger.error(f"[EngineerAgent] Refactoring failed: {e}")
            return {
                "changes": [],
                "error": str(e)
            }
    
    async def prepare_context_for_implementer(self, task_spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare detailed context and specifications for Implementer.
        
        Args:
            task_spec: Task specification from Architect
            
        Returns:
            Prepared context with clear implementation instructions
        """
        logger.info("[EngineerAgent] Preparing context for Implementer")
        
        # Gather necessary information
        context = {
            "task_overview": task_spec.get("description", ""),
            "requirements": task_spec.get("requirements", []),
            "constraints": task_spec.get("constraints", []),
            "existing_code_references": [],
            "test_requirements": task_spec.get("tests_needed", []),
            "implementation_steps": task_spec.get("steps", []),
            "success_criteria": task_spec.get("success_criteria", [])
        }
        
        # Enhance with actual code references if available
        if "file_paths" in task_spec:
            context["existing_code_references"] = task_spec["file_paths"]
        
        return context
    
    async def validate_tool_execution(self, tool_name: str, result: Dict[str, Any]) -> bool:
        """
        Validate that a tool execution completed successfully.
        
        Args:
            tool_name: Name of the executed tool
            result: Tool execution result
            
        Returns:
            True if execution was successful, False otherwise
        """
        if tool_name == "execute_command":
            return result.get("exit_code", -1) == 0
        elif tool_name == "read_workspace_file":
            return "content" in result and result.get("success", False)
        elif tool_name == "write_workspace_file":
            return result.get("success", False)
        elif tool_name == "search_grep":
            return result.get("success", False)
        else:
            return result.get("success", False)
    
    def _format_requirements(self, requirements: Dict[str, Any]) -> str:
        """Format requirements dictionary as readable text."""
        lines = []
        for key, value in requirements.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context dictionary as readable text."""
        if not context:
            return "No additional context provided."
        
        lines = []
        for key, value in context.items():
            lines.append(f"{key}: {str(value)[:500]}")
        return "\n".join(lines)
    
    def _format_feedback(self, feedback: Dict[str, Any]) -> str:
        """Format feedback dictionary as readable text."""
        lines = []
        for key, value in feedback.items():
            lines.append(f"{key}: {str(value)[:300]}")
        return "\n".join(lines)
    
    async def _execute_setup_steps(self, steps: List[Dict[str, Any]], project_id: str) -> List[Dict[str, Any]]:
        """Execute environment setup steps via tools."""
        execution_log = []
        
        for step in steps:
            command = step.get("command", "")
            expected = step.get("expected_outcome", "")
            
            try:
                result = await self._tool_dispatcher.execute(
                    tool_name="execute_command",
                    arguments={
                        "command": command,
                        "timeout": 120
                    }
                )
                
                success = result.get("exit_code", -1) == 0
                
                execution_log.append({
                    "step": step.get("name", "Unknown"),
                    "command": command,
                    "success": success,
                    "output": result.get("output", "")[:500],
                    "expected": expected
                })
                
                if not success:
                    logger.warning(f"[EngineerAgent] Setup step failed: {command}")
                    
            except Exception as e:
                execution_log.append({
                    "step": step.get("name", "Unknown"),
                    "command": command,
                    "success": False,
                    "error": str(e)
                })
        
        return execution_log
    
    async def _analyze_test_output(self, output: str) -> Dict[str, Any]:
        """Analyze test output to extract pass/fail statistics."""
        prompt = f"""
Analyze this test output and extract:
- total_tests: Total number of tests run
- passed_tests: Number of tests that passed
- failed_tests: Number of tests that failed
- failed_test_names: Names of failed tests (if identifiable)
- error_messages: Key error messages (summarized)
- all_passed: Boolean indicating if all tests passed

Test output:
{output[:3000]}

Respond in JSON format."""
        
        try:
            response = await self._orchestrator.generate_async(
                messages=[
                    {"role": "system", "content": "Extract test statistics. Respond in JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            # Parse JSON response
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[EngineerAgent] Failed to analyze test output: {e}")
        
        # Fallback: simple regex-based analysis
        return {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "failed_test_names": [],
            "error_messages": [output[:500]] if output else [],
            "all_passed": "passed" in output.lower() and "failed" not in output.lower()
        }
    
    def _parse_setup_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into setup structure."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                parsed = json.loads(response[start:end])
                return {
                    "status": "PLANNED",
                    "steps": parsed.get("steps", []),
                    "execution_log": []
                }
        except Exception as e:
            logger.warning(f"[EngineerAgent] Failed to parse setup response: {e}")
        
        return {
            "status": "FAILED",
            "steps": [],
            "execution_log": [],
            "error": "Failed to parse setup plan"
        }
    
    def _parse_error_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into error analysis structure."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[EngineerAgent] Failed to parse error analysis: {e}")
        
        return {
            "root_cause": "Analysis unavailable",
            "hypothesis": [],
            "suggested_fixes": [],
            "diagnostic_commands": [],
            "files_to_change": []
        }
    
    def _parse_refactor_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into refactoring structure."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[EngineerAgent] Failed to parse refactor response: {e}")
        
        return {
            "changes": [],
            "error": "Failed to parse refactoring plan"
        }
