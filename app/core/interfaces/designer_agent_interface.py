from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IDesignerAgentService(ABC):
    """
    Interface for Designer Agent Service in ATM mode.
    Responsible for UI/UX design, frontend code, content generation, and visual fixes.
    """
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
