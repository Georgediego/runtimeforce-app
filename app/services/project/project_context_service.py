"""
Project Context Service

Manages project-specific context including attached files, rules, and architectural guidelines.
Injects context into AI agent prompts via AgentContextBuilder.
"""

from typing import Optional, Dict, Any, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ProjectContextService:
    """Service for managing project context and configurations."""

    def __init__(self):
        pass

    def build_context_prompt(
        self,
        project_id: str,
        context_data: Optional[Dict[str, Any]] = None,
        rules: Optional[List[str]] = None,
        attached_files: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Build a comprehensive context prompt for AI agents.

        Args:
            project_id: Project identifier
            context_data: Project context metadata
            rules: List of project rules/guidelines
            attached_files: List of attached context files

        Returns:
            Formatted context prompt string
        """
        prompt_sections = []

        # Project header
        prompt_sections.append(f"# Project Context: {project_id}")
        prompt_sections.append("")

        # Add context metadata
        if context_data:
            prompt_sections.append("## Project Information")
            if 'name' in context_data:
                prompt_sections.append(f"**Name:** {context_data['name']}")
            if 'description' in context_data:
                prompt_sections.append(f"**Description:** {context_data['description']}")
            if 'tech_stack' in context_data:
                stack = ', '.join(context_data['tech_stack'])
                prompt_sections.append(f"**Tech Stack:** {stack}")
            prompt_sections.append("")

        # Add architectural guidelines
        if context_data and 'architecture' in context_data:
            prompt_sections.append("## Architecture Guidelines")
            prompt_sections.append(context_data['architecture'])
            prompt_sections.append("")

        # Add rules
        if rules:
            prompt_sections.append("## Project Rules")
            for i, rule in enumerate(rules, 1):
                prompt_sections.append(f"{i}. {rule}")
            prompt_sections.append("")

        # Add attached files content
        if attached_files:
            prompt_sections.append("## Attached Context Files")
            for file_info in attached_files:
                filename = file_info.get('filename', 'unknown')
                content = file_info.get('content', '')
                
                prompt_sections.append(f"### File: {filename}")
                prompt_sections.append("```")
                prompt_sections.append(content)
                prompt_sections.append("```")
                prompt_sections.append("")

        return "\n".join(prompt_sections)

    def extract_workflow_from_context(
        self,
        context_data: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Extract workflow steps from project context.

        Args:
            context_data: Project context with workflow definition

        Returns:
            List of workflow steps
        """
        if not context_data or 'workflow' not in context_data:
            # Default workflow
            return [
                "Analyze requirements",
                "Write code",
                "Run tests",
                "Update changelog",
                "Commit changes"
            ]

        workflow = context_data.get('workflow', [])
        if isinstance(workflow, str):
            # Parse comma-separated or newline-separated workflow
            if '\n' in workflow:
                return [step.strip() for step in workflow.split('\n') if step.strip()]
            elif ',' in workflow:
                return [step.strip() for step in workflow.split(',') if step.strip()]
            else:
                return [workflow]

        return workflow

    def validate_context_size(
        self,
        context_prompt: str,
        max_tokens: int = 4000
    ) -> Dict[str, Any]:
        """
        Validate context prompt size against token limits.

        Args:
            context_prompt: Built context prompt
            max_tokens: Maximum allowed tokens

        Returns:
            Validation result dictionary
        """
        # Rough token estimation (4 chars ≈ 1 token)
        estimated_tokens = len(context_prompt) // 4

        is_within_limit = estimated_tokens <= max_tokens

        return {
            'is_valid': is_within_limit,
            'estimated_tokens': estimated_tokens,
            'max_tokens': max_tokens,
            'characters': len(context_prompt),
            'truncation_needed': not is_within_limit,
            'truncation_ratio': max_tokens / estimated_tokens if estimated_tokens > max_tokens else 1.0
        }

    def truncate_context_safely(
        self,
        context_prompt: str,
        max_tokens: int = 4000,
        preserve_sections: Optional[List[str]] = None
    ) -> str:
        """
        Safely truncate context while preserving important sections.

        Args:
            context_prompt: Original context prompt
            max_tokens: Maximum allowed tokens
            preserve_sections: Section headers to preserve

        Returns:
            Truncated context prompt
        """
        if preserve_sections is None:
            preserve_sections = ['Project Rules', 'Architecture Guidelines']

        # Split into sections
        lines = context_prompt.split('\n')
        sections = []
        current_section = []
        current_header = None

        for line in lines:
            if line.startswith('#'):
                if current_section:
                    sections.append({
                        'header': current_header,
                        'content': '\n'.join(current_section)
                    })
                current_header = line
                current_section = [line]
            else:
                current_section.append(line)

        if current_section:
            sections.append({
                'header': current_header,
                'content': '\n'.join(current_section)
            })

        # Calculate tokens per section
        section_tokens = []
        for section in sections:
            tokens = len(section['content']) // 4
            section_tokens.append({
                **section,
                'tokens': tokens,
                'is_priority': any(
                    header in (section['header'] or '')
                    for header in preserve_sections
                )
            })

        # Sort by priority (preserve important sections first)
        section_tokens.sort(key=lambda x: (not x['is_priority'], x['tokens']))

        # Build truncated context
        result_sections = []
        total_tokens = 0

        for section in section_tokens:
            if total_tokens + section['tokens'] <= max_tokens:
                result_sections.append(section['content'])
                total_tokens += section['tokens']
            elif section['is_priority']:
                # Always include priority sections, even if over limit
                result_sections.insert(0, section['content'])
                total_tokens += section['tokens']

        return '\n'.join(result_sections)

    def get_context_for_agent(
        self,
        project_id: str,
        agent_role: str,
        context_data: Optional[Dict[str, Any]] = None,
        rules: Optional[List[str]] = None,
        attached_files: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Get optimized context for a specific agent role.

        Args:
            project_id: Project identifier
            agent_role: Role of the agent ('architect', 'engineer', 'implementer', 'designer')
            context_data: Project context
            rules: Project rules
            attached_files: Attached context files

        Returns:
            Role-specific context prompt
        """
        base_context = self.build_context_prompt(
            project_id=project_id,
            context_data=context_data,
            rules=rules,
            attached_files=attached_files
        )

        # Add role-specific instructions
        role_instructions = {
            'architect': (
                "\n\n## Your Role as Architect\n"
                "- Focus on high-level design and architecture\n"
                "- Decompose tasks into clear steps\n"
                "- Review code for adherence to guidelines\n"
                "- Ensure Definition of Done is met"
            ),
            'engineer': (
                "\n\n## Your Role as Engineer\n"
                "- Bridge between architecture and implementation\n"
                "- Set up testing environments\n"
                "- Analyze errors and debug issues\n"
                "- Prepare data for implementers and designers"
            ),
            'implementer': (
                "\n\n## Your Role as Implementer\n"
                "- Write clean, functional code\n"
                "- Generate tests for your code\n"
                "- Apply fixes based on feedback\n"
                "- Work with files directly"
            ),
            'designer': (
                "\n\n## Your Role as Designer\n"
                "- Design UI/UX components\n"
                "- Write HTML/CSS/JavaScript code\n"
                "- Generate content and images\n"
                "- Ensure visual consistency"
            )
        }

        instruction = role_instructions.get(agent_role, '')
        return base_context + instruction

    def format_rules_for_prompt(self, rules: List[str]) -> str:
        """
        Format rules list for inclusion in prompts.

        Args:
            rules: List of rule strings

        Returns:
            Formatted rules section
        """
        if not rules:
            return ""

        formatted = ["## Project Rules and Guidelines\n"]
        for i, rule in enumerate(rules, 1):
            formatted.append(f"{i}. {rule}")

        return "\n".join(formatted)

    def merge_contexts(
        self,
        global_context: Optional[str],
        project_context: Optional[str],
        session_context: Optional[str]
    ) -> str:
        """
        Merge multiple context sources with proper prioritization.

        Args:
            global_context: Global user settings/context
            project_context: Project-specific context
            session_context: Current session context

        Returns:
            Merged context string
        """
        parts = []

        # Order: Global → Project → Session (most specific last)
        if global_context:
            parts.append("# Global Context\n")
            parts.append(global_context)
            parts.append("")

        if project_context:
            parts.append("# Project Context\n")
            parts.append(project_context)
            parts.append("")

        if session_context:
            parts.append("# Session Context\n")
            parts.append(session_context)

        return "\n".join(parts)
