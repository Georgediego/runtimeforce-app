"""
Git Routing Service

Intelligent Git branch routing based on version tags and commit patterns.
Determines target branch for pushes based on SemVer/CalVer conventions.
"""

from typing import Optional, Tuple, List
import re
import logging

logger = logging.getLogger(__name__)


class GitRoutingService:
    """Service for intelligent Git branch routing decisions."""

    # Branch naming conventions
    MAIN_BRANCHES = ['main', 'master', 'trunk']
    DEV_BRANCHES = ['dev', 'develop', 'development']
    RELEASE_PREFIX = 'release/'
    FEATURE_PREFIX = 'feature/'
    HOTFIX_PREFIX = 'hotfix/'

    # Version pattern matching
    SEMVER_PATTERN = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z]+)(\d+)?)?$')
    CALVER_PATTERN = re.compile(r'^v?(\d{4})\.(\d{2})\.(\d{2})(?:-(\d+\.\d+\.\d+))?$')

    def __init__(self):
        pass

    def determine_target_branch(
        self,
        version_tag: Optional[str] = None,
        current_branch: Optional[str] = None,
        available_branches: Optional[List[str]] = None,
        custom_rules: Optional[dict] = None
    ) -> str:
        """
        Determine the target branch for a push based on version and context.

        Args:
            version_tag: Version tag being pushed (e.g., 'v1.2.3', 'v2024.07.31')
            current_branch: Current git branch name
            available_branches: List of available remote branches
            custom_rules: Custom routing rules from project config

        Returns:
            Target branch name for push
        """
        # Apply custom rules first if provided
        if custom_rules:
            custom_result = self._apply_custom_rules(
                version_tag, current_branch, custom_rules
            )
            if custom_result:
                return custom_result

        # Analyze version type
        version_type = self._analyze_version_type(version_tag)

        # Route based on version type
        if version_type == 'major':
            return self._find_branch('main', available_branches)
        elif version_type == 'minor':
            return self._find_branch('main', available_branches)
        elif version_type == 'patch':
            return self._find_branch('main', available_branches)
        elif version_type == 'prerelease':
            return self._find_branch('release', available_branches, version_tag)
        elif version_type == 'calver':
            return self._find_branch('main', available_branches)
        else:
            # Default to dev branch for non-versioned commits
            return self._find_branch('dev', available_branches)

    def _analyze_version_type(self, version_tag: Optional[str]) -> Optional[str]:
        """
        Analyze version tag to determine its type.

        Args:
            version_tag: Version tag string

        Returns:
            Version type: 'major', 'minor', 'patch', 'prerelease', 'calver', or None
        """
        if not version_tag:
            return None

        # Remove 'v' prefix if present
        tag = version_tag.lstrip('v')

        # Check CalVer first
        if self.CALVER_PATTERN.match(tag):
            return 'calver'

        # Check SemVer
        match = self.SEMVER_PATTERN.match(tag)
        if match:
            major, minor, patch, prerelease, prerelease_num = match.groups()

            if prerelease:
                return 'prerelease'

            major_int = int(major)
            minor_int = int(minor)
            patch_int = int(patch)

            # Simple heuristic: if minor changed, it's minor release
            # This is simplified - real logic would compare with previous version
            if minor_int > 0 and patch_int == 0:
                return 'minor'
            elif patch_int > 0:
                return 'patch'
            elif major_int > 0:
                return 'major'

        return None

    def _find_branch(
        self,
        branch_type: str,
        available_branches: Optional[List[str]],
        version_tag: Optional[str] = None
    ) -> str:
        """
        Find appropriate branch name based on type and availability.

        Args:
            branch_type: Type of branch ('main', 'dev', 'release')
            available_branches: List of available branches
            version_tag: Version tag for release branches

        Returns:
            Best matching branch name
        """
        if not available_branches:
            # Return default names if no branches provided
            if branch_type == 'main':
                return 'main'
            elif branch_type == 'dev':
                return 'dev'
            elif branch_type == 'release' and version_tag:
                return f'{self.RELEASE_PREFIX}{version_tag}'
            return 'main'

        # Look for exact matches
        if branch_type == 'main':
            for branch in self.MAIN_BRANCHES:
                if branch in available_branches:
                    return branch
            # Fallback to first branch containing 'main' or 'master'
            for branch in available_branches:
                if 'main' in branch.lower() or 'master' in branch.lower():
                    return branch

        elif branch_type == 'dev':
            for branch in self.DEV_BRANCHES:
                if branch in available_branches:
                    return branch
            # Fallback to first branch containing 'dev'
            for branch in available_branches:
                if 'dev' in branch.lower():
                    return branch

        elif branch_type == 'release' and version_tag:
            release_branch = f'{self.RELEASE_PREFIX}{version_tag}'
            if release_branch in available_branches:
                return release_branch
            # Create new release branch name
            return release_branch

        # Ultimate fallback
        return available_branches[0] if available_branches else 'main'

    def _apply_custom_rules(
        self,
        version_tag: Optional[str],
        current_branch: Optional[str],
        custom_rules: dict
    ) -> Optional[str]:
        """
        Apply custom routing rules from project configuration.

        Args:
            version_tag: Version tag
            current_branch: Current branch
            custom_rules: Custom rules dictionary

        Returns:
            Target branch if rule matches, None otherwise
        """
        if not custom_rules:
            return None

        # Example custom rule structure:
        # {
        #     "branch_patterns": {
        #         "feature/.*": "develop",
        #         "hotfix/.*": "main",
        #         "release/v\\d+.*": "main"
        #     },
        #     "version_rules": {
        #         "prerelease": "staging",
        #         "major": "next"
        #     }
        # }

        branch_patterns = custom_rules.get('branch_patterns', {})
        if current_branch:
            for pattern, target in branch_patterns.items():
                if re.match(pattern, current_branch):
                    logger.info(f"Custom rule matched: {current_branch} -> {target}")
                    return target

        version_rules = custom_rules.get('version_rules', {})
        if version_tag:
            version_type = self._analyze_version_type(version_tag)
            if version_type and version_type in version_rules:
                target = version_rules[version_type]
                logger.info(f"Version rule matched: {version_tag} ({version_type}) -> {target}")
                return target

        return None

    def get_routing_decision_explanation(
        self,
        version_tag: Optional[str],
        current_branch: Optional[str],
        target_branch: str
    ) -> str:
        """
        Generate human-readable explanation for routing decision.

        Args:
            version_tag: Version tag used
            current_branch: Source branch
            target_branch: Determined target branch

        Returns:
            Explanation string
        """
        parts = []

        if current_branch:
            parts.append(f"From branch '{current_branch}'")

        if version_tag:
            version_type = self._analyze_version_type(version_tag)
            parts.append(f"version {version_tag} ({version_type or 'unknown'} type)")

        if target_branch in self.MAIN_BRANCHES:
            parts.append("routing to main production branch")
        elif target_branch in self.DEV_BRANCHES:
            parts.append("routing to development branch")
        elif target_branch.startswith(self.RELEASE_PREFIX):
            parts.append("routing to release branch")
        elif target_branch.startswith(self.FEATURE_PREFIX):
            parts.append("routing to feature branch")
        elif target_branch.startswith(self.HOTFIX_PREFIX):
            parts.append("routing to hotfix branch")
        else:
            parts.append(f"routing to '{target_branch}'")

        return ", ".join(parts).capitalize() + "."

    def validate_branch_name(self, branch_name: str) -> Tuple[bool, Optional[str]]:
        """
        Validate branch name against Git conventions and safety rules.

        Args:
            branch_name: Branch name to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not branch_name:
            return False, "Branch name cannot be empty"

        if len(branch_name) > 255:
            return False, "Branch name is too long (max 255 characters)"

        # Git reserved characters
        reserved_chars = ['~', '^', ':', '\\', '?', '*', '[', ' ']
        for char in reserved_chars:
            if char in branch_name:
                return False, f"Branch name contains invalid character: '{char}'"

        # Cannot start or end with slash
        if branch_name.startswith('/') or branch_name.endswith('/'):
            return False, "Branch name cannot start or end with '/'"

        # Cannot have consecutive slashes
        if '//' in branch_name:
            return False, "Branch name cannot contain consecutive slashes"

        # Cannot end with .lock
        if branch_name.endswith('.lock'):
            return False, "Branch name cannot end with '.lock'"

        # Check for dangerous patterns
        dangerous_patterns = ['HEAD', '..', '@{']
        for pattern in dangerous_patterns:
            if pattern in branch_name:
                return False, f"Branch name contains dangerous pattern: '{pattern}'"

        return True, None
