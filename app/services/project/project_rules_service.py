"""
Project Rules Service

Manages project-specific rules and guidelines for AI agents.
Parses, validates, and formats rules from project configuration.
"""

from typing import Optional, Dict, Any, List, Tuple
import logging
import re

logger = logging.getLogger(__name__)


class ProjectRulesService:
    """Service for managing project rules and guidelines."""

    # Rule categories
    CATEGORIES = {
        'code_style': ['formatting', 'naming', 'indentation', 'style'],
        'architecture': ['pattern', 'layer', 'module', 'component', 'interface'],
        'testing': ['test', 'coverage', 'assertion', 'mock', 'fixture'],
        'security': ['security', 'auth', 'encrypt', 'sanitize', 'validate'],
        'performance': ['performance', 'optimize', 'cache', 'async'],
        'documentation': ['docstring', 'comment', 'readme', 'api']
    }

    def __init__(self):
        pass

    def parse_rules_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Parse rules from a text document.

        Args:
            text: Raw text containing rules

        Returns:
            List of parsed rule dictionaries
        """
        rules = []

        # Split by common rule markers
        lines = text.split('\n')
        current_rule = None
        current_category = 'general'

        for line in lines:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Check for numbered rules (1. 2. 3.)
            numbered_match = re.match(r'^(\d+)[\.\)]\s*(.+)$', line)
            if numbered_match:
                if current_rule:
                    rules.append(current_rule)
                
                rule_text = numbered_match.group(2)
                current_rule = {
                    'text': rule_text,
                    'category': self._categorize_rule(rule_text),
                    'priority': int(numbered_match.group(1))
                }
                continue

            # Check for bullet points (- * •)
            bullet_match = re.match(r'^[-*•]\s*(.+)$', line)
            if bullet_match:
                if current_rule:
                    rules.append(current_rule)
                
                rule_text = bullet_match.group(1)
                current_rule = {
                    'text': rule_text,
                    'category': self._categorize_rule(rule_text),
                    'priority': 999  # Bullet points have lower priority
                }
                continue

            # Continuation of previous rule
            if current_rule:
                current_rule['text'] += ' ' + line

        # Add last rule
        if current_rule:
            rules.append(current_rule)

        return rules

    def _categorize_rule(self, rule_text: str) -> str:
        """
        Automatically categorize a rule based on keywords.

        Args:
            rule_text: Rule text

        Returns:
            Category name
        """
        text_lower = rule_text.lower()

        for category, keywords in self.CATEGORIES.items():
            if any(keyword in text_lower for keyword in keywords):
                return category

        return 'general'

    def validate_rule(self, rule_text: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a single rule for clarity and actionability.

        Args:
            rule_text: Rule to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not rule_text or not rule_text.strip():
            return False, "Rule cannot be empty"

        if len(rule_text) < 10:
            return False, "Rule is too short (minimum 10 characters)"

        if len(rule_text) > 500:
            return False, "Rule is too long (maximum 500 characters)"

        # Check for actionable language
        action_words = [
            'must', 'should', 'always', 'never', 'require',
            'ensure', 'avoid', 'use', 'do not', 'don\'t'
        ]

        has_action_word = any(word in rule_text.lower() for word in action_words)
        if not has_action_word:
            logger.warning(f"Rule may not be actionable: {rule_text[:50]}")

        # Check for conflicting terms
        conflicts = [
            ('always', 'never'),
            ('must', 'optional'),
            ('required', 'optional')
        ]

        for word1, word2 in conflicts:
            if word1 in rule_text.lower() and word2 in rule_text.lower():
                return False, f"Rule contains conflicting terms: '{word1}' and '{word2}'"

        return True, None

    def validate_rules_list(self, rules: List[str]) -> Dict[str, Any]:
        """
        Validate a list of rules.

        Args:
            rules: List of rule strings

        Returns:
            Validation results dictionary
        """
        results = {
            'valid_count': 0,
            'invalid_count': 0,
            'warnings': [],
            'errors': [],
            'validated_rules': []
        }

        for i, rule in enumerate(rules):
            is_valid, error = self.validate_rule(rule)

            if is_valid:
                results['valid_count'] += 1
                results['validated_rules'].append({
                    'index': i,
                    'text': rule,
                    'category': self._categorize_rule(rule)
                })
            else:
                results['invalid_count'] += 1
                results['errors'].append({
                    'index': i,
                    'rule': rule[:50],
                    'error': error
                })

        # Check for duplicate rules
        seen_rules = set()
        for rule_data in results['validated_rules']:
            normalized = rule_data['text'].lower().strip()
            if normalized in seen_rules:
                results['warnings'].append(f"Duplicate rule detected: {rule_data['text'][:50]}")
            seen_rules.add(normalized)

        # Check for contradictory rules
        results['warnings'].extend(self._check_contradictions(rules))

        return results

    def _check_contradictions(self, rules: List[str]) -> List[str]:
        """
        Check for potentially contradictory rules.

        Args:
            rules: List of rules

        Returns:
            List of warning messages
        """
        warnings = []
        contradictions = []

        # Look for obvious contradictions
        always_rules = [r for r in rules if 'always' in r.lower()]
        never_rules = [r for r in rules if 'never' in r.lower()]

        for always_rule in always_rules:
            for never_rule in never_rules:
                # Simple keyword overlap check
                always_words = set(always_rule.lower().split())
                never_words = set(never_rule.lower().split())
                overlap = always_words & never_words

                # If significant overlap, flag as potential contradiction
                if len(overlap) >= 3:
                    contradictions.append(
                        f"Potential contradiction between:\n"
                        f"  - '{always_rule[:50]}'\n"
                        f"  - '{never_rule[:50]}'"
                    )

        return contradictions

    def format_rules_for_system_prompt(
        self,
        rules: List[Dict[str, Any]],
        max_rules: int = 20
    ) -> str:
        """
        Format rules for inclusion in system prompt.

        Args:
            rules: List of rule dictionaries
            max_rules: Maximum number of rules to include

        Returns:
            Formatted rules string
        """
        if not rules:
            return ""

        # Sort by priority
        sorted_rules = sorted(rules, key=lambda x: x.get('priority', 999))

        # Limit to max_rules
        limited_rules = sorted_rules[:max_rules]

        formatted = ["## Project Rules\n"]
        for i, rule in enumerate(limited_rules, 1):
            text = rule.get('text', '')
            category = rule.get('category', 'general')
            
            formatted.append(f"{i}. [{category.upper()}] {text}")

        if len(rules) > max_rules:
            formatted.append(f"\n... and {len(rules) - max_rules} more rules")

        return "\n".join(formatted)

    def extract_rules_from_markdown(self, markdown_content: str) -> List[Dict[str, Any]]:
        """
        Extract rules from a Markdown document.

        Args:
            markdown_content: Markdown content

        Returns:
            List of extracted rule dictionaries
        """
        rules = []

        # Look for sections with rules
        section_pattern = r'#+\s*(?:rules?|guidelines?|standards?)(.*?)#+\s*\w'
        sections = re.findall(section_pattern, markdown_content, re.IGNORECASE | re.DOTALL)

        for section in sections:
            # Parse rules within section
            section_rules = self.parse_rules_from_text(section)
            rules.extend(section_rules)

        # Also look for inline rules
        inline_pattern = r'[-*•]\s*(?:must|should|always|never|require)[^.\n]+[.\n]'
        inline_matches = re.findall(inline_pattern, markdown_content, re.IGNORECASE)

        for match in inline_matches:
            rule_text = match.strip('-*• \n')
            rules.append({
                'text': rule_text,
                'category': self._categorize_rule(rule_text),
                'priority': 999,
                'source': 'inline'
            })

        return rules

    def get_rules_by_category(
        self,
        rules: List[Dict[str, Any]],
        category: str
    ) -> List[Dict[str, Any]]:
        """
        Filter rules by category.

        Args:
            rules: List of rule dictionaries
            category: Category to filter by

        Returns:
            Filtered list of rules
        """
        return [
            rule for rule in rules
            if rule.get('category') == category
        ]

    def merge_rule_sets(
        self,
        global_rules: List[Dict[str, Any]],
        project_rules: List[Dict[str, Any]],
        override_duplicates: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Merge global and project-specific rules.

        Args:
            global_rules: Global user rules
            project_rules: Project-specific rules
            override_duplicates: Whether project rules override global duplicates

        Returns:
            Merged list of rules
        """
        merged = []
        seen_texts = set()

        # Add project rules first (higher priority)
        for rule in project_rules:
            normalized = rule['text'].lower().strip()
            merged.append(rule)
            seen_texts.add(normalized)

        # Add global rules (unless duplicate)
        for rule in global_rules:
            normalized = rule['text'].lower().strip()
            
            if override_duplicates and normalized in seen_texts:
                logger.debug(f"Skipping duplicate rule: {rule['text'][:50]}")
                continue
            
            merged.append(rule)

        return merged
