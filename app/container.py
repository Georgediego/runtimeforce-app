import logging
from typing import Any, Dict, Optional

# Core Events & Interfaces
from app.core.events.event_bus import EventBus
from app.core.interfaces.rotation_service_interface import IRotationService
from app.core.interfaces.workspace_driver_factory_interface import IWorkspaceDriverFactory
from app.core.interfaces.embedding_engine_interface import IEmbeddingEngine

# Database Connection Manager
from app.repository.db_connection import DatabaseConnectionManager

# Repositories
from app.repository.conversation_db_repository import ConversationDBRepository
from app.repository.workspace_db_repository import WorkspaceDBRepository
from app.repository.provider_keys_db_repository import ProviderKeysDBRepository
from app.repository.ssh_keys_db_repository import SSHKeysDBRepository
from app.repository.telemetry_db_repository import TelemetryDBRepository
from app.repository.subscription_db_repository import SubscriptionDBRepository
from app.repository.audit_local_db_repository import AuditLocalDBRepository
from app.repository.support_ticket_db_repository import SupportTicketDBRepository
from app.repository.project_db_repository import ProjectDBRepository
from app.repository.versioning_db_repository import VersioningDBRepository
from app.repository.social_feed_db_repository import SocialFeedDBRepository
from app.repository.graph_db_repository import GraphDBRepository
from app.repository.decision_db_repository import DecisionDBRepository
from app.repository.embeddings_db_repository import EmbeddingsDBRepository
from app.repository.oauth_db_repository import OAuthDBRepository

# Workspace & Project Services
from app.services.workspace.workspace_driver_factory import WorkspaceDriverFactory
from app.services.workspace.workspace_manager_service import WorkspaceManagerService
from app.services.project.project_service import ProjectService
from app.services.ssh.ssh_connection_pool import SSHConnectionPool

# Memory Services
from app.services.memory.graph_traversal_service import GraphTraversalService
from app.services.memory.context_cache_service import ContextCacheService
from app.services.memory.local_embedding_service import LocalEmbeddingService
from app.services.memory.graph_memory_service import GraphMemoryService
from app.services.memory.file_intelligence_service import FileIntelligenceService
from app.services.memory.context_builder_service import ContextBuilderService
from app.services.memory.decision_recorder_service import DecisionRecorderService
from app.services.memory.terminal_intelligence_service import TerminalIntelligenceService

# LLM Services
from app.services.llm.llm_registry_service import LLMRegistryService
from app.services.llm.llm_discovery_service import LLMDiscoveryService
from app.services.llm.llm_router_service import LLMRouterService
from app.services.llm.llm_scoring_service import LLMScoringService
from app.services.llm.llm_orchestrator_service import LLMOrchestratorService
from app.services.llm.llm_rotation_service import LLMRotationService

# Agent Services
from app.services.agent.architect_agent_service import ArchitectAgentService
from app.services.agent.role_router_service import RoleRouterService
from app.services.agent.agent_loop_coordinator import AgentLoopCoordinator

# Git & OAuth Services
from app.services.git.github_oauth_service import GitHubOAuthService
from app.services.git.github_api_service import GitHubApiService

# Social Media Services
from app.services.social.x_oauth_service import XOAuthService
from app.services.social.reddit_oauth_service import RedditOAuthService

# Tools Services
from app.services.terminal.terminal_command_filter import TerminalCommandFilter
from app.tools.tool_dispatcher_service import ToolDispatcherService

# Auxiliary Services
from app.services.billing.license_service import LicenseService
from app.services.billing.credit_balance_service import CreditBalanceService
from app.services.byok.byok_key_service import ByokKeyService
from app.services.audit.audit_logger_service import AuditLoggerService
from app.services.support.support_ticket_service import SupportTicketService
from app.services.versioning.version_calculator_service import VersionCalculatorService
from app.services.versioning.changelog_generator_service import ChangelogGeneratorService
from app.services.social.social_post_generator_service import SocialPostGeneratorService
from app.services.social.social_feedback_listener_service import SocialFeedbackListenerService

logger = logging.getLogger(__name__)

class ApplicationContainer:
    def __init__(self) -> None:
        self._services: Dict[Any, Any] = {}
        self._named_services: Dict[str, Any] = {}
        self.bootstrap()

    @property
    def workspace_repository(self):
        return self.workspace_repo

    @property
    def conversation_repository(self):
        return self.conversation_repo

    def register(self, interface_cls: Any, instance: Any, name: Optional[str] = None) -> None:
        self._services[interface_cls] = instance
        if name:
            self._named_services[name] = instance

    def resolve(self, interface_cls: Any) -> Any:
        if interface_cls not in self._services:
            raise KeyError(f"Service for interface {interface_cls.__name__} is not registered in container.")
        return self._services[interface_cls]

    def resolve_by_name(self, name: str) -> Any:
        if name in self._named_services:
            return self._named_services[name]
        raise KeyError(f"Named service '{name}' is not registered in container.")

    def bootstrap(self) -> None:
        logger.info("[DI Container] Bootstrapping RuntimeForce production container...")
        
        self.event_bus = EventBus()
        self.db_manager = DatabaseConnectionManager()
        
        self.conversation_repo = ConversationDBRepository(self.db_manager)
        self.workspace_repo = WorkspaceDBRepository(self.db_manager)
        self.provider_keys_repo = ProviderKeysDBRepository(self.db_manager)
        self.ssh_keys_repo = SSHKeysDBRepository(self.db_manager)
        self.telemetry_repo = TelemetryDBRepository(self.db_manager)
        self.subscription_repo = SubscriptionDBRepository(self.db_manager)
        self.audit_repo = AuditLocalDBRepository(self.db_manager)
        self.support_ticket_repo = SupportTicketDBRepository(self.db_manager)
        self.project_repo = ProjectDBRepository(self.db_manager)
        self.versioning_repo = VersioningDBRepository(self.db_manager)
        self.social_feed_repo = SocialFeedDBRepository(self.db_manager)
        self.graph_repo = GraphDBRepository(self.db_manager)
        self.decision_repo = DecisionDBRepository(self.db_manager)
        self.oauth_repo = OAuthDBRepository(self.db_manager)
        
        self.local_embedding_service = LocalEmbeddingService()
        self.embeddings_repo = EmbeddingsDBRepository(self.db_manager, embedding_engine=self.local_embedding_service)
        
        self.ssh_pool = SSHConnectionPool()
        self.workspace_driver_factory = WorkspaceDriverFactory(self.ssh_keys_repo, self.ssh_pool)
        self.workspace_manager_service = WorkspaceManagerService(
            self.workspace_repo,
            self.workspace_driver_factory,
            project_repo=self.project_repo
        )
        
        self.version_calculator_service = VersionCalculatorService(version_repo=self.versioning_repo, event_bus=self.event_bus)
        self.project_service = ProjectService(
            self.project_repo,
            version_calculator=self.version_calculator_service,
            workspace_repo=self.workspace_repo
        )
        
        self.license_service = LicenseService()
        self.credit_balance_service = CreditBalanceService()
        self.byok_key_service = ByokKeyService(keys_repo=self.provider_keys_repo, license_service=self.license_service)
        self.audit_logger_service = AuditLoggerService(repo=self.audit_repo, event_bus=self.event_bus)
        self.support_ticket_service = SupportTicketService(self.support_ticket_repo)
        self.changelog_generator_service = ChangelogGeneratorService()
        self.social_post_generator_service = SocialPostGeneratorService(social_repo=self.social_feed_repo, event_bus=self.event_bus)
        self.social_feedback_listener_service = SocialFeedbackListenerService(self.social_feed_repo)
        
        self.graph_traversal_service = GraphTraversalService(graph_repo=self.graph_repo)
        self.context_cache_service = ContextCacheService()
        self.graph_memory_service = GraphMemoryService(
            graph_repo=self.graph_repo,
            embeddings_repo=self.embeddings_repo
        )
        self.file_intelligence_service = FileIntelligenceService(graph_memory=self.graph_memory_service)
        self.context_builder_service = ContextBuilderService(
            graph_memory=self.graph_memory_service,
            decision_repo=self.decision_repo,
            graph_traversal=self.graph_traversal_service,
            context_cache=self.context_cache_service,
            embeddings_repo=self.embeddings_repo
        )
        self.decision_recorder_service = DecisionRecorderService(
            decision_repo=self.decision_repo,
            graph_memory=self.graph_memory_service
        )
        self.terminal_intelligence_service = TerminalIntelligenceService(graph_memory=self.graph_memory_service)
        
        self.llm_rotation_service = LLMRotationService(event_bus=self.event_bus)
        self.llm_registry = LLMRegistryService()
        self.llm_discovery = LLMDiscoveryService(registry_service=self.llm_registry)
        self.llm_router = LLMRouterService(registry_service=self.llm_registry, rotation_service=self.llm_rotation_service)
        self.llm_scoring = LLMScoringService(telemetry_repo=self.telemetry_repo, rotation_service=self.llm_rotation_service)
        self.llm_orchestrator = LLMOrchestratorService(
            provider_keys_repo=self.provider_keys_repo,
            llm_registry=self.llm_registry,
            rotation_service=self.llm_rotation_service
        )
        
        self.architect_agent_service = ArchitectAgentService(
            llm_orchestrator=self.llm_orchestrator,
            context_builder=self.context_builder_service,
            event_bus=self.event_bus
        )
        
        self.terminal_command_filter = TerminalCommandFilter()
        self.tool_dispatcher_service = ToolDispatcherService(command_filter=self.terminal_command_filter)
        
        # Initialize OAuth services
        self.github_oauth_service = GitHubOAuthService(oauth_repository=self.oauth_repo)
        self.github_api_service = GitHubApiService()
        self.x_oauth_service = XOAuthService(oauth_repository=self.oauth_repo)
        self.reddit_oauth_service = RedditOAuthService(oauth_repository=self.oauth_repo)
        
        self.role_router_service = RoleRouterService()

        self.agent_loop_coordinator = AgentLoopCoordinator(
            orchestrator_service=self.llm_orchestrator,
            architect_agent=self.architect_agent_service,
            storage_repository=self.graph_repo,
            conversation_repo=self.conversation_repo,
            context_builder=self.context_builder_service,
            project_service=self.project_service,
            rotation_service=self.llm_rotation_service,
            event_bus=self.event_bus,
            graph_memory=self.graph_memory_service,
            provider_keys_repo=self.provider_keys_repo,
            role_router=self.role_router_service,
            llm_router=self.llm_router,
        )
        
        self.register(EventBus, self.event_bus, name="event_bus")
        self.register(DatabaseConnectionManager, self.db_manager, name="db_manager")
        self.register(IRotationService, self.llm_rotation_service, name="rotation_service")
        self.register(LLMRotationService, self.llm_rotation_service, name="rotation_service_impl")
        self.register(IEmbeddingEngine, self.local_embedding_service, name="embedding_engine")
        self.register(IWorkspaceDriverFactory, self.workspace_driver_factory, name="workspace_driver_factory")
        self.register(ArchitectAgentService, self.architect_agent_service, name="architect_agent")
        self.register(AgentLoopCoordinator, self.agent_loop_coordinator, name="agent_coordinator")
        self.register(LLMOrchestratorService, self.llm_orchestrator, name="llm_orchestrator")
        self.register(FileIntelligenceService, self.file_intelligence_service, name="file_intelligence")
        
        # Register OAuth services
        self.register(GitHubOAuthService, self.github_oauth_service, name="github_oauth")
        self.register(GitHubApiService, self.github_api_service, name="github_api")
        self.register(XOAuthService, self.x_oauth_service, name="x_oauth")
        self.register(RedditOAuthService, self.reddit_oauth_service, name="reddit_oauth")
        
        self._named_services.update({
            "event_bus": self.event_bus,
            "db_manager": self.db_manager,
            "conversation_repo": self.conversation_repo,
            "conversation_repository": self.conversation_repo,
            "workspace_repo": self.workspace_repo,
            "workspace_repository": self.workspace_repo,
            "provider_keys_repo": self.provider_keys_repo,
            "ssh_keys_repo": self.ssh_keys_repo,
            "telemetry_repo": self.telemetry_repo,
            "subscription_repo": self.subscription_repo,
            "audit_repo": self.audit_repo,
            "support_ticket_repo": self.support_ticket_repo,
            "project_repo": self.project_repo,
            "versioning_repo": self.versioning_repo,
            "social_feed_repo": self.social_feed_repo,
            "graph_repo": self.graph_repo,
            "decision_repo": self.decision_repo,
            "oauth_repo": self.oauth_repo,
            "embeddings_repo": self.embeddings_repo,
            "storage_repo": self.graph_repo,
            "workspace_manager": self.workspace_manager_service,
            "workspace_driver_factory": self.workspace_driver_factory,
            "project_service": self.project_service,
            "graph_memory": self.graph_memory_service,
            "file_intelligence": self.file_intelligence_service,
            "context_builder": self.context_builder_service,
            "decision_recorder": self.decision_recorder_service,
            "terminal_intelligence": self.terminal_intelligence_service,
            "llm_registry": self.llm_registry,
            "llm_discovery": self.llm_discovery,
            "llm_router": self.llm_router,
            "llm_scoring": self.llm_scoring,
            "llm_rotation": self.llm_rotation_service,
            "architect_agent": self.architect_agent_service,
            "agent_coordinator": self.agent_loop_coordinator,
            "tool_dispatcher": self.tool_dispatcher_service,
            "license_service": self.license_service,
            "credit_balance": self.credit_balance_service,
            "byok_key_service": self.byok_key_service,
            "audit_logger": self.audit_logger_service,
            "support_ticket_service": self.support_ticket_service,
            "version_calculator": self.version_calculator_service,
            "changelog_generator": self.changelog_generator_service,
            "social_post_generator": self.social_post_generator_service,
            "social_feedback_listener": self.social_feedback_listener_service,
        })

container = ApplicationContainer()

def get_container() -> ApplicationContainer:
    return container

def get_event_bus() -> EventBus:
    return container.event_bus

def get_db_manager() -> DatabaseConnectionManager:
    return container.db_manager

def get_conversation_repo() -> ConversationDBRepository:
    return container.conversation_repo

def get_workspace_repo() -> WorkspaceDBRepository:
    return container.workspace_repo

def get_provider_keys_repo() -> ProviderKeysDBRepository:
    return container.provider_keys_repo

def get_ssh_keys_repo() -> SSHKeysDBRepository:
    return container.ssh_keys_repo

def get_ssh_pool() -> SSHConnectionPool:
    return container.ssh_pool

def get_telemetry_repo() -> TelemetryDBRepository:
    return container.telemetry_repo

def get_subscription_repo() -> SubscriptionDBRepository:
    return container.subscription_repo

def get_audit_repo() -> AuditLocalDBRepository:
    return container.audit_repo

def get_support_ticket_repo() -> SupportTicketDBRepository:
    return container.support_ticket_repo

def get_project_repo() -> ProjectDBRepository:
    return container.project_repo

def get_versioning_repo() -> VersioningDBRepository:
    return container.versioning_repo

def get_social_feed_repo() -> SocialFeedDBRepository:
    return container.social_feed_repo

def get_graph_repo() -> GraphDBRepository:
    return container.graph_repo

def get_decision_repo() -> DecisionDBRepository:
    return container.decision_repo

def get_embeddings_repo() -> EmbeddingsDBRepository:
    return container.embeddings_repo

def get_storage_repo() -> GraphDBRepository:
    return container.graph_repo

def get_workspace_manager() -> WorkspaceManagerService:
    return container.workspace_manager_service

def get_project_service() -> ProjectService:
    return container.project_service

def get_graph_memory() -> GraphMemoryService:
    return container.graph_memory_service

def get_graph_memory_service() -> GraphMemoryService:
    return container.graph_memory_service

def get_file_intelligence() -> FileIntelligenceService:
    return container.file_intelligence_service

def get_context_builder() -> ContextBuilderService:
    return container.context_builder_service

def get_context_builder_service() -> ContextBuilderService:
    return container.context_builder_service

def get_decision_recorder() -> DecisionRecorderService:
    return container.decision_recorder_service

def get_terminal_intelligence() -> TerminalIntelligenceService:
    return container.terminal_intelligence_service

def get_llm_registry() -> LLMRegistryService:
    return container.llm_registry

def get_llm_discovery() -> LLMDiscoveryService:
    return container.llm_discovery

def get_llm_router() -> LLMRouterService:
    return container.llm_router

def get_llm_scoring() -> LLMScoringService:
    return container.llm_scoring

def get_llm_orchestrator() -> LLMOrchestratorService:
    return container.llm_orchestrator

def get_rotation_service() -> IRotationService:
    return container.llm_rotation_service

def get_architect_agent() -> ArchitectAgentService:
    return container.architect_agent_service

def get_agent_coordinator() -> AgentLoopCoordinator:
    return container.agent_loop_coordinator

def get_license_service() -> LicenseService:
    return container.license_service

def get_credit_balance() -> CreditBalanceService:
    return container.credit_balance_service

def get_credit_service() -> CreditBalanceService:
    return container.credit_balance_service

def get_byok_key_service() -> ByokKeyService:
    return container.byok_key_service

def get_audit_logger() -> AuditLoggerService:
    return container.audit_logger_service

def get_audit_service() -> AuditLoggerService:
    return container.audit_logger_service

def get_support_ticket_service() -> SupportTicketService:
    return container.support_ticket_service

def get_support_service() -> SupportTicketService:
    return container.support_ticket_service

def get_version_calculator() -> VersionCalculatorService:
    return container.version_calculator_service

def get_changelog_generator() -> ChangelogGeneratorService:
    return container.changelog_generator_service

def get_social_post_generator() -> SocialPostGeneratorService:
    return container.social_post_generator_service

def get_social_service() -> SocialPostGeneratorService:
    return container.social_post_generator_service

def get_social_feedback_listener() -> SocialFeedbackListenerService:
    return container.social_feedback_listener_service

def get_github_api() -> GitHubApiService:
    return container.github_api_service
