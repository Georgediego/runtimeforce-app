"""
Support Bot Service

Automated support bot for common questions and triage.
Provides instant responses for FAQs and routes complex issues to human support.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class SupportBotService:
    """Service for automated support responses and triage."""

    # FAQ patterns and responses
    FAQ_PATTERNS = {
        r'install|installation|setup': {
            'response': (
                "To install RuntimeForce:\n"
                "1. Clone the repository\n"
                "2. Run `pip install -r requirements.txt`\n"
                "3. Configure your API keys in Settings\n"
                "4. Start with `python -m app.main`\n\n"
                "For detailed instructions, visit our documentation."
            ),
            'severity': 'low'
        },
        r'api[_-]?key|byok|provider': {
            'response': (
                "To configure BYOK (Bring Your Own Key):\n"
                "1. Go to Settings → API Providers\n"
                "2. Select your provider (OpenAI, Anthropic, etc.)\n"
                "3. Click 'Get Free Key' or enter your existing key\n"
                "4. Keys are encrypted locally with AES-256-GCM\n\n"
                "Your keys never leave your machine unencrypted."
            ),
            'severity': 'low'
        },
        r'ssh|connect|remote|vps': {
            'response': (
                "To connect to a remote VPS via SSH:\n"
                "1. Open Project Settings → Workspace & SSH\n"
                "2. Add SSH host details (host, port, user)\n"
                "3. Use password or SSH key authentication\n"
                "4. Test connection before saving\n\n"
                "SSH credentials are stored encrypted locally."
            ),
            'severity': 'medium'
        },
        r'credit|balance|billing|subscription|paddle': {
            'response': (
                "Billing information:\n"
                "- Free tier: $0/month with limited features\n"
                "- Pro: $19/month with 5,000 AI credits\n"
                "- Studio: $49/month with 15,000 AI credits + full BYOK\n\n"
                "We use Paddle as Merchant of Record. "
                "Check your subscription status in Settings → Billing."
            ),
            'severity': 'medium'
        },
        r'git|push|commit|branch|version': {
            'response': (
                "Git integration features:\n"
                "- Automatic branch routing based on version tags\n"
                "- SemVer and CalVer support\n"
                "- Auto-push on version bump (configurable)\n"
                "- Git diff visualization in UI\n\n"
                "Configure in Project Settings → Git & GitHub."
            ),
            'severity': 'low'
        },
        r'error|bug|crash|fail|issue|problem': {
            'response': (
                "Sorry you're experiencing issues! Let's help you:\n"
                "1. Check the terminal output for error messages\n"
                "2. Review logs in Settings → Audit\n"
                "3. Try restarting the application\n"
                "4. If the issue persists, create a support ticket\n\n"
                "Would you like me to create a support ticket for you?"
            ),
            'severity': 'high'
        },
        r'project|workspace|directory|path': {
            'response': (
                "Project management:\n"
                "- Create new projects from the Projects menu\n"
                "- Each project has isolated settings and context\n"
                "- Workspace can be local directory or remote SSH\n"
                "- Maximum projects: Free=1, Pro=3, Studio=5\n\n"
                "Switch between projects in the top bar."
            ),
            'severity': 'low'
        },
        r'model|llm|ai|chat|orchestrator': {
            'response': (
                "AI Model configuration:\n"
                "- AUTO mode: Orchestrator selects optimal model\n"
                "- ATM mode: Multi-agent team (Architect, Engineer, Implementer, Designer)\n"
                "- LOCAL mode: Only local models (Ollama, LM Studio)\n"
                "- MANUAL mode: Fixed model selection (Studio only)\n\n"
                "Select models in Settings → API Providers."
            ),
            'severity': 'low'
        }
    }

    # Escalation keywords that require human support
    ESCALATION_KEYWORDS = [
        'legal', 'lawsuit', 'lawyer', 'attorney',
        'refund', 'chargeback', 'cancel subscription',
        'data breach', 'security issue', 'vulnerability',
        'gdpr', 'privacy', 'delete my data',
        'enterprise', 'custom', 'integration'
    ]

    def __init__(self):
        pass

    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Analyze user query and determine response strategy.

        Args:
            query: User's support question

        Returns:
            Analysis result dictionary
        """
        query_lower = query.lower()

        # Check for escalation keywords
        needs_escalation = any(
            keyword in query_lower
            for keyword in self.ESCALATION_KEYWORDS
        )

        # Find matching FAQ patterns
        matches = []
        for pattern, faq_data in self.FAQ_PATTERNS.items():
            if re.search(pattern, query_lower):
                matches.append((pattern, faq_data))

        # Determine best response
        if needs_escalation:
            return {
                'type': 'escalation',
                'requires_human': True,
                'suggested_severity': 'high',
                'auto_response': self._get_escalation_response(),
                'matched_faqs': []
            }

        if matches:
            # Use the first match (could be improved with scoring)
            _, best_match = matches[0]
            return {
                'type': 'faq',
                'requires_human': False,
                'response': best_match['response'],
                'severity': best_match['severity'],
                'matched_patterns': [m[0] for m in matches],
                'matched_faqs': matches
            }

        # No match found
        return {
            'type': 'unknown',
            'requires_human': True,
            'suggested_severity': 'medium',
            'auto_response': self._get_fallback_response(),
            'matched_faqs': []
        }

    def _get_escalation_response(self) -> str:
        """Get response for escalated issues."""
        return (
            "This issue requires assistance from our support team.\n\n"
            "I'll create a priority ticket for you. "
            "A team member will respond within 24 hours.\n\n"
            "For urgent matters, contact support@runtimeforce.dev"
        )

    def _get_fallback_response(self) -> str:
        """Get fallback response when no FAQ matches."""
        return (
            "I couldn't find a specific answer to your question in our knowledge base.\n\n"
            "Here are some helpful resources:\n"
            "- Documentation: https://docs.runtimeforce.dev\n"
            "- Community Forum: https://community.runtimeforce.dev\n"
            "- Status Page: https://status.runtimeforce.dev\n\n"
            "Would you like me to create a support ticket?"
        )

    def generate_response(self, query: str) -> Tuple[str, bool]:
        """
        Generate automated response for a support query.

        Args:
            query: User's question

        Returns:
            Tuple of (response_text, needs_human_followup)
        """
        analysis = self.analyze_query(query)

        if analysis['type'] == 'faq':
            return analysis['response'], False

        elif analysis['type'] == 'escalation':
            return analysis['auto_response'], True

        else:  # unknown
            return analysis['auto_response'], True

    def suggest_ticket_category(self, query: str) -> str:
        """
        Suggest support ticket category based on query.

        Args:
            query: User's question

        Returns:
            Category name
        """
        query_lower = query.lower()

        if any(word in query_lower for word in ['billing', 'payment', 'subscription', 'refund']):
            return 'billing'
        elif any(word in query_lower for word in ['bug', 'error', 'crash', 'fail']):
            return 'technical'
        elif any(word in query_lower for word in ['feature', 'request', 'suggestion']):
            return 'feature_request'
        elif any(word in query_lower for word in ['account', 'login', 'auth']):
            return 'account'
        elif any(word in query_lower for word in ['security', 'vulnerability', 'breach']):
            return 'security'
        else:
            return 'general'

    def get_priority_score(self, query: str, user_tier: str = 'free') -> int:
        """
        Calculate priority score for a support ticket.

        Args:
            query: User's question
            user_tier: User's subscription tier

        Returns:
            Priority score (1-10, higher = more urgent)
        """
        score = 3  # Base score
        query_lower = query.lower()

        # Severity indicators
        if any(word in query_lower for word in ['critical', 'urgent', 'asap', 'emergency']):
            score += 3

        if any(word in query_lower for word in ['down', 'broken', 'not working']):
            score += 2

        # Security issues get highest priority
        if any(word in query_lower for word in ['security', 'breach', 'vulnerability']):
            score += 4

        # Paid tiers get slight priority boost
        if user_tier == 'pro':
            score += 1
        elif user_tier == 'studio':
            score += 2

        return min(score, 10)  # Cap at 10

    def create_auto_response_log(
        self,
        query: str,
        response: str,
        needs_followup: bool,
        category: str
    ) -> Dict[str, Any]:
        """
        Create log entry for automated response.

        Args:
            query: Original user query
            response: Bot response provided
            needs_followup: Whether human followup is needed
            category: Ticket category

        Returns:
            Log entry dictionary
        """
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'query_preview': query[:100],
            'response_provided': True,
            'needs_followup': needs_followup,
            'category': category,
            'bot_confidence': 'high' if not needs_followup else 'low'
        }

    def should_create_ticket(self, query: str, user_satisfied: Optional[bool] = None) -> bool:
        """
        Determine if a support ticket should be created.

        Args:
            query: User's question
            user_satisfied: Explicit satisfaction feedback (if available)

        Returns:
            True if ticket should be created
        """
        # Explicit dissatisfaction
        if user_satisfied is False:
            return True

        analysis = self.analyze_query(query)

        # Always create ticket for escalations
        if analysis['requires_human']:
            return True

        # Create ticket for high severity issues
        if analysis.get('severity') == 'high':
            return True

        return False
