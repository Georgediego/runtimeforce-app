"""
BYOK Safety Service

Validates and sanitizes BYOK API keys before storage and usage.
Ensures keys are properly formatted, not compromised, and safe to use.
"""

from typing import Optional, Tuple, Dict, Any
import re
import hashlib
import logging

logger = logging.getLogger(__name__)


class BYOKSafetyService:
    """Service for validating and securing BYOK API keys."""

    # Known key patterns for different providers
    KEY_PATTERNS = {
        'openai': r'^sk-[a-zA-Z0-9]{20,}$',
        'anthropic': r'^sk-ant-[a-zA-Z0-9_-]{20,}$',
        'google': r'^[a-zA-Z0-9_-]{39}$',
        'groq': r'^gsk_[a-zA-Z0-9]{40,}$',
        'cerebras': r'^csb_[a-zA-Z0-9]{40,}$',
        'sambanova': r'^[a-zA-Z0-9]{40,}$',
        'deepseek': r'^sk-[a-zA-Z0-9]{20,}$',
        'xai': r'^xai-[a-zA-Z0-9]{20,}$',
        'perplexity': r'^pplx-[a-zA-Z0-9]{40,}$',
        'openrouter': r'^sk-or-[a-zA-Z0-9]{20,}$',
    }

    # Known compromised or test key prefixes (example list)
    BLOCKED_PREFIXES = [
        'sk-test',
        'sk-example',
        'placeholder',
        'your_',
        'xxx',
    ]

    def __init__(self):
        pass

    def validate_key_format(
        self,
        key: str,
        provider: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate API key format for a specific provider.

        Args:
            key: The API key to validate
            provider: Provider name (e.g., 'openai', 'anthropic')

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not key or not isinstance(key, str):
            return False, "Key must be a non-empty string"

        key = key.strip()

        if len(key) < 10:
            return False, "Key is too short"

        if len(key) > 500:
            return False, "Key is suspiciously long"

        pattern = self.KEY_PATTERNS.get(provider.lower())
        if pattern:
            if not re.match(pattern, key):
                return False, f"Key does not match expected format for {provider}"

        # Check for blocked prefixes
        for prefix in self.BLOCKED_PREFIXES:
            if key.lower().startswith(prefix):
                return False, "Key appears to be a placeholder or example"

        return True, None

    def sanitize_key(self, key: str) -> str:
        """
        Sanitize API key by removing whitespace and invisible characters.

        Args:
            key: Raw API key

        Returns:
            Sanitized key
        """
        if not key:
            return ""

        # Remove common whitespace characters
        key = key.strip()
        key = key.replace('\n', '').replace('\r', '')
        key = key.replace(' ', '')

        # Remove invisible Unicode characters
        key = ''.join(c for c in key if ord(c) >= 32 or ord(c) == 0)

        return key

    def check_key_entropy(self, key: str, min_entropy: float = 3.5) -> Tuple[bool, float]:
        """
        Calculate Shannon entropy of the key to detect weak keys.

        Args:
            key: API key to analyze
            min_entropy: Minimum acceptable entropy threshold

        Returns:
            Tuple of (is_acceptable, entropy_value)
        """
        import math
        from collections import Counter

        if not key:
            return False, 0.0

        # Calculate frequency of each character
        freq = Counter(key)
        length = len(key)

        # Calculate Shannon entropy
        entropy = 0.0
        for count in freq.values():
            probability = count / length
            entropy -= probability * math.log2(probability)

        return entropy >= min_entropy, entropy

    def generate_key_fingerprint(self, key: str) -> str:
        """
        Generate a unique fingerprint for the key (for logging/identification).

        Args:
            key: API key

        Returns:
            SHA256 fingerprint (first 16 chars)
        """
        if not key:
            return ""

        fingerprint = hashlib.sha256(key.encode('utf-8')).hexdigest()
        return fingerprint[:16]

    def mask_key_for_display(self, key: str, visible_chars: int = 4) -> str:
        """
        Mask API key for safe display in UI/logs.

        Args:
            key: API key to mask
            visible_chars: Number of characters to show at start and end

        Returns:
            Masked key (e.g., 'sk-proj****...****xyz')
        """
        if not key or len(key) <= visible_chars * 2:
            return '*' * len(key) if key else ""

        start = key[:visible_chars]
        end = key[-visible_chars:]
        middle_length = len(key) - visible_chars * 2

        return f"{start}{'*' * middle_length}{end}"

    def validate_key_safety(
        self,
        key: str,
        provider: str
    ) -> Dict[str, Any]:
        """
        Perform comprehensive safety validation on an API key.

        Args:
            key: API key to validate
            provider: Provider name

        Returns:
            Dictionary with validation results
        """
        result = {
            'is_safe': False,
            'is_valid_format': False,
            'has_sufficient_entropy': False,
            'entropy_value': 0.0,
            'fingerprint': '',
            'masked_key': '',
            'errors': [],
            'warnings': []
        }

        # Sanitize first
        sanitized_key = self.sanitize_key(key)

        if not sanitized_key:
            result['errors'].append("Key is empty after sanitization")
            return result

        result['masked_key'] = self.mask_key_for_display(sanitized_key)
        result['fingerprint'] = self.generate_key_fingerprint(sanitized_key)

        # Validate format
        is_valid, error = self.validate_key_format(sanitized_key, provider)
        result['is_valid_format'] = is_valid
        if not is_valid:
            result['errors'].append(error or "Invalid key format")

        # Check entropy
        has_entropy, entropy = self.check_key_entropy(sanitized_key)
        result['has_sufficient_entropy'] = has_entropy
        result['entropy_value'] = entropy
        if not has_entropy:
            result['warnings'].append(
                f"Key entropy ({entropy:.2f}) is below recommended threshold"
            )

        # Overall safety
        result['is_safe'] = (
            result['is_valid_format'] and
            result['has_sufficient_entropy'] and
            len(result['errors']) == 0
        )

        return result

    def is_likely_test_key(self, key: str) -> bool:
        """
        Detect if a key is likely a test/placeholder key.

        Args:
            key: API key to check

        Returns:
            True if likely a test key
        """
        if not key:
            return True

        key_lower = key.lower()

        # Common test patterns
        test_patterns = [
            'test',
            'example',
            'sample',
            'demo',
            'placeholder',
            'your_key',
            'api_key',
            'xxx',
            '12345',
        ]

        for pattern in test_patterns:
            if pattern in key_lower:
                return True

        # Check for repeated characters (weak key)
        if len(set(key)) < len(key) * 0.3:
            return True

        return False
