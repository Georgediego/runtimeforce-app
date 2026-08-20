"""
Designer Agent Service - UI/UX and content specialist in ATM mode.
Responsible for UI design, frontend code, content generation, and visual fixes.
"""

import logging
from typing import Any, Dict, List, Optional
import json

from app.core.events.event_bus import EventBus
from app.core.interfaces.designer_agent_interface import IDesignerAgentService

logger = logging.getLogger(__name__)


class DesignerAgentService(IDesignerAgentService):
    """
    Designer role in Autonomous Team Mode (ATM).
    
    Responsibilities:
    - Design and implement UI/UX components
    - Write frontend code (HTML/CSS/JavaScript/TypeScript)
    - Generate content (text, copy, documentation)
    - Create visual assets descriptions (for image generation tools)
    - Apply visual and UX fixes based on feedback
    - Ensure responsive design and accessibility
    - Maintain design consistency across the application
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
        
        self._system_prompt = """You are the Designer in an autonomous development team.
Your responsibilities:
1. Design intuitive and beautiful UI/UX components
2. Write clean, semantic HTML/CSS/JavaScript/TypeScript code
3. Generate engaging content, copy, and documentation
4. Create visual asset descriptions for image generation tools
5. Apply visual and UX fixes based on feedback
6. Ensure responsive design across all device sizes
7. Implement accessibility best practices (WCAG compliance)
8. Maintain design consistency with existing style guides

Always focus on:
- User experience and usability
- Visual aesthetics and modern design trends
- Performance optimization (lazy loading, minification)
- Cross-browser compatibility
- Mobile-first responsive design
- Accessibility for all users
- Brand consistency

Respond in structured JSON format when reporting progress."""

    async def design_ui_component(
        self,
        component_spec: Dict[str, Any],
        project_id: str
    ) -> Dict[str, Any]:
        """
        Design and implement a UI component.
        
        Args:
            component_spec: Component specification (type, features, style)
            project_id: Project identifier
            
        Returns:
            Component implementation with code files and assets
        """
        logger.info(f"[DesignerAgent] Designing UI component for project {project_id}")
        
        prompt = f"""
Component specification:
{self._format_component_spec(component_spec)}

Design and implement this component:
1. Create semantic HTML structure
2. Write modern, maintainable CSS (or Tailwind classes)
3. Implement interactive behavior with JavaScript/TypeScript
4. Ensure responsive design for mobile, tablet, desktop
5. Add accessibility features (ARIA labels, keyboard navigation)
6. Follow existing project design patterns

Provide complete code for:
- Component file(s) (.tsx, .vue, .jsx, or .html)
- Styles file(s) (.css, .scss, .module.css)
- Any required assets or icons

Format response as JSON with file contents."""
        
        try:
            context = await self._context_builder.build_optimal_context(
                project_id=project_id,
                user_prompt=f"Design UI component: {component_spec.get('name', 'Unknown')}"
            )
            
            response = await self._orchestrator.generate_with_context(
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                context=context,
                temperature=0.3
            )
            
            component_plan = self._parse_component_response(response)
            
            # Write component files
            execution_results = await self._write_component_files(
                component_plan.get("files", []),
                project_id
            )
            
            result = {
                "status": "COMPLETED",
                "component_name": component_spec.get("name", "Unknown"),
                "files_created": len(execution_results),
                "execution_results": execution_results
            }
            
            if self._event_bus:
                await self._event_bus.publish("designer.component_designed", {
                    "project_id": project_id,
                    "component": component_spec.get("name", "Unknown"),
                    "files_count": len(execution_results)
                })
            
            return result
        except Exception as e:
            logger.error(f"[DesignerAgent] UI component design failed: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "files_created": 0
            }
    
    async def generate_content(
        self,
        content_type: str,
        topic: str,
        requirements: Dict[str, Any],
        project_id: str
    ) -> Dict[str, Any]:
        """
        Generate content (text, copy, documentation).
        
        Args:
            content_type: Type of content (landing page, docs, blog post, etc.)
            topic: Content topic or subject
            requirements: Content requirements (tone, length, audience)
            project_id: Project identifier
            
        Returns:
            Generated content ready for use
        """
        logger.info(f"[DesignerAgent] Generating {content_type} content about {topic}")
        
        prompt = f"""
Content type: {content_type}
Topic: {topic}

Requirements:
{self._format_requirements(requirements)}

Generate high-quality content:
1. Engaging and clear writing
2. Appropriate tone for target audience
3. Proper structure and formatting
4. SEO-friendly (if applicable)
5. Call-to-action where appropriate
6. Consistent with brand voice

Provide:
- content: The generated text content
- title: Suggested title
- meta_description: SEO meta description (if applicable)
- word_count: Approximate word count

Format response as JSON."""
        
        try:
            context = await self._context_builder.build_optimal_context(
                project_id=project_id,
                user_prompt=f"Generate {content_type} content about {topic}"
            )
            
            response = await self._orchestrator.generate_with_context(
                system_prompt=self._system_prompt,
                user_prompt=prompt,
                context=context,
                temperature=0.5
            )
            
            return self._parse_content_response(response)
        except Exception as e:
            logger.error(f"[DesignerAgent] Content generation failed: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "content": ""
            }
    
    async def create_visual_asset_description(
        self,
        asset_type: str,
        description: str,
        style_guide: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create detailed description for visual asset generation.
        
        Args:
            asset_type: Type of asset (logo, banner, icon, screenshot)
            description: What the asset should depict
            style_guide: Brand colors, fonts, style preferences
            
        Returns:
            Detailed prompt for image generation AI
        """
        logger.info(f"[DesignerAgent] Creating {asset_type} asset description")
        
        prompt = f"""
Asset type: {asset_type}
Description: {description}

Style guide:
{self._format_style_guide(style_guide)}

Create a detailed prompt for AI image generation:
1. Describe composition and layout
2. Specify colors matching brand guidelines
3. Include style references (modern, minimal, bold, etc.)
4. Mention technical requirements (dimensions, format)
5. Add mood and atmosphere descriptors

Provide:
- image_prompt: Detailed prompt for image generation AI
- dimensions: Suggested dimensions (e.g., 1200x630)
- format: Recommended format (PNG, SVG, JPG)
- color_palette: Hex codes of primary colors used

Format response as JSON."""
        
        try:
            response = await self._orchestrator.generate_async(
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4
            )
            
            return self._parse_asset_response(response)
        except Exception as e:
            logger.error(f"[DesignerAgent] Asset description creation failed: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "image_prompt": ""
            }
    
    async def apply_visual_fix(
        self,
        fix_description: str,
        file_path: str,
        current_content: str,
        project_id: str
    ) -> Dict[str, Any]:
        """
        Apply visual/UX fix to existing component.
        
        Args:
            fix_description: What needs to be fixed visually
            file_path: Path to the file needing fixes
            current_content: Current file content
            project_id: Project identifier
            
        Returns:
            Fixed code and summary of visual changes
        """
        logger.info(f"[DesignerAgent] Applying visual fix to {file_path}")
        
        prompt = f"""
File: {file_path}

Current content:
{current_content[:3000]}

Visual fix required:
{fix_description}

Apply the visual fix:
1. Identify CSS/ styling issues
2. Fix layout, spacing, colors, typography
3. Ensure responsive behavior
4. Maintain accessibility
5. Keep design consistency

Provide:
- fixed_content: Complete updated file content
- visual_changes: List of specific visual improvements
- before_after_notes: What changed visually

Format response as JSON."""
        
        try:
            response = await self._orchestrator.generate_async(
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            
            fix_result = self._parse_visual_fix_response(response)
            
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
            logger.error(f"[DesignerAgent] Visual fix failed: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "fixed_content": ""
            }
    
    async def ensure_responsive_design(
        self,
        component_files: List[str],
        project_id: str
    ) -> Dict[str, Any]:
        """
        Review and ensure responsive design across breakpoints.
        
        Args:
            component_files: List of component file paths to review
            project_id: Project identifier
            
        Returns:
            Responsive design audit with recommendations
        """
        logger.info(f"[DesignerAgent] Auditing responsive design for {len(component_files)} files")
        
        # Read all component files
        file_contents = {}
        for file_path in component_files:
            read_result = await self._tool_dispatcher.execute(
                tool_name="read_workspace_file",
                arguments={"file_path": file_path}
            )
            if read_result.get("success", False):
                file_contents[file_path] = read_result.get("content", "")
        
        prompt = f"""
Review these component files for responsive design:

{self._format_file_contents(file_contents)}

Audit for responsive design:
1. Check mobile-first approach
2. Verify breakpoints (mobile, tablet, desktop)
3. Test touch targets and spacing
4. Ensure readable typography at all sizes
5. Check image scaling
6. Verify flexible layouts (Flexbox/Grid)

Provide:
- audit_results: Pass/Fail for each breakpoint
- issues: List of responsive design issues found
- recommendations: Specific fixes needed
- priority: HIGH/MEDIUM/LOW

Format response as JSON."""
        
        try:
            response = await self._orchestrator.generate_async(
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            
            return self._parse_responsive_audit_response(response)
        except Exception as e:
            logger.error(f"[DesignerAgent] Responsive audit failed: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "audit_results": {},
                "issues": []
            }
    
    def _format_component_spec(self, spec: Dict[str, Any]) -> str:
        """Format component specification as readable text."""
        lines = []
        lines.append(f"Name: {spec.get('name', 'Unknown')}")
        lines.append(f"Type: {spec.get('type', 'Component')}")
        lines.append(f"Features: {spec.get('features', [])}")
        lines.append(f"Style: {spec.get('style', 'Modern')}")
        return "\n".join(lines)
    
    def _format_requirements(self, requirements: Dict[str, Any]) -> str:
        """Format content requirements as readable text."""
        lines = []
        for key, value in requirements.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)
    
    def _format_style_guide(self, style_guide: Dict[str, Any]) -> str:
        """Format style guide as readable text."""
        lines = []
        if "colors" in style_guide:
            lines.append(f"Colors: {style_guide['colors']}")
        if "fonts" in style_guide:
            lines.append(f"Fonts: {style_guide['fonts']}")
        if "style" in style_guide:
            lines.append(f"Style: {style_guide['style']}")
        return "\n".join(lines)
    
    def _format_file_contents(self, file_contents: Dict[str, str]) -> str:
        """Format multiple file contents as readable text."""
        lines = []
        for filepath, content in file_contents.items():
            lines.append(f"\n--- {filepath} ---\n{content[:1000]}")
        return "\n".join(lines)
    
    async def _write_component_files(
        self,
        files: List[Dict[str, Any]],
        project_id: str
    ) -> List[Dict[str, Any]]:
        """Write component files to workspace."""
        results = []
        
        for file_op in files:
            filepath = file_op.get("filepath", "")
            content = file_op.get("content", "")
            
            try:
                result = await self._tool_dispatcher.execute(
                    tool_name="write_workspace_file",
                    arguments={
                        "file_path": filepath,
                        "content": content
                    }
                )
                
                results.append({
                    "filepath": filepath,
                    "success": result.get("success", False),
                    "result": result
                })
                
            except Exception as e:
                results.append({
                    "filepath": filepath,
                    "success": False,
                    "error": str(e)
                })
        
        return results
    
    def _parse_component_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into component plan."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[DesignerAgent] Failed to parse component response: {e}")
        
        return {
            "files": [],
            "error": "Failed to parse component plan"
        }
    
    def _parse_content_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into content."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[DesignerAgent] Failed to parse content response: {e}")
        
        return {
            "content": "",
            "title": "",
            "error": "Failed to parse content"
        }
    
    def _parse_asset_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into asset description."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[DesignerAgent] Failed to parse asset response: {e}")
        
        return {
            "image_prompt": "",
            "dimensions": "1200x630",
            "format": "PNG"
        }
    
    def _parse_visual_fix_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into visual fix result."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[DesignerAgent] Failed to parse visual fix response: {e}")
        
        return {
            "fixed_content": "",
            "visual_changes": [],
            "before_after_notes": ""
        }
    
    def _parse_responsive_audit_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into responsive audit result."""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except Exception as e:
            logger.warning(f"[DesignerAgent] Failed to parse responsive audit response: {e}")
        
        return {
            "audit_results": {},
            "issues": [],
            "recommendations": []
        }
