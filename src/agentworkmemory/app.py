from collections.abc import Sequence

from agentworkmemory.database import open_database
from agentworkmemory.integrations.auto_distillation import (
    default_auto_distill_scheduler_adapter,
)
from agentworkmemory.integrations.automation import default_scheduler_adapter
from agentworkmemory.integrations.curators import (
    OllamaCuratorAdapter,
    YokeCuratorAdapter,
)
from agentworkmemory.integrations.improvement import (
    CodexImprovementProposer,
    GitRevisionReader,
)
from agentworkmemory.integrations.processes import PsutilActivityProcessProbe
from agentworkmemory.integrations.remotes import SshRemoteSnapshotAdapter
from agentworkmemory.integrations.transcripts import (
    ClaudeTranscriptCollector,
    CodexTranscriptCollector,
    CursorTranscriptCollector,
)
from agentworkmemory.integrations.vault_repository import (
    GitVaultRepositoryAdapter,
)
from agentworkmemory.services.activity import ActivityService
from agentworkmemory.services.auto_distillation.ports import (
    AutoDistillSchedulerAdapter,
)
from agentworkmemory.services.auto_distillation.service import (
    AutoDistillationService,
)
from agentworkmemory.services.auto_distillation.store import AutoDistillStore
from agentworkmemory.services.automation.ports import SchedulerAdapter
from agentworkmemory.services.automation.service import AutomationService
from agentworkmemory.services.automation.store import AutomationStore
from agentworkmemory.services.curators.ports import CuratorAdapter
from agentworkmemory.services.curators.service import CuratorsService
from agentworkmemory.services.diagnostics import DiagnosticsService
from agentworkmemory.services.distillation.service import DistillationService
from agentworkmemory.services.distillation.store import DistillationStore
from agentworkmemory.services.improvement import ImprovementService, ImprovementStore
from agentworkmemory.services.improvement.ports import ImprovementProposer
from agentworkmemory.services.remotes.ports import RemoteSnapshotAdapter
from agentworkmemory.services.remotes.service import RemotesService
from agentworkmemory.services.remotes.store import RemoteStore
from agentworkmemory.services.search import SearchService
from agentworkmemory.services.sessions import SessionsService
from agentworkmemory.services.sessions.store import SessionsStore
from agentworkmemory.services.synchronization.service import SynchronizationService
from agentworkmemory.services.synchronization.store import SynchronizationStore
from agentworkmemory.services.translations import TranslationService
from agentworkmemory.services.vault import VaultService
from agentworkmemory.services.vault_repository import (
    VaultRepositoryAdapter,
    VaultRepositoryService,
)
from agentworkmemory.services.viewer import ViewerService
from agentworkmemory.services.wiki import WikiCatalogService
from agentworkmemory.settings import AgentWorkMemoryConfig, load_config
from agentworkmemory.workflows.auto_distill import AutoDistillWorkflow
from agentworkmemory.workflows.collect import CollectAgentRecordsWorkflow
from agentworkmemory.workflows.distill import DistillSessionsWorkflow
from agentworkmemory.workflows.distill.coordination import DistillCoordination
from agentworkmemory.workflows.import_legacy import ImportLegacyAlmanacWorkflow
from agentworkmemory.workflows.import_records import ImportAgentRecordsWorkflow
from agentworkmemory.workflows.improve_harness import ImproveHarnessWorkflow
from agentworkmemory.workflows.remote_sync import SyncRemoteRecordsWorkflow
from agentworkmemory.workflows.setup import SetupAgentWorkMemoryWorkflow
from agentworkmemory.workflows.sync import SyncAgentRecordsWorkflow
from agentworkmemory.workflows.translate import TranslateWikiWorkflow
from agentworkmemory.workflows.vault_repository import VaultRepositoryWorkflow


class AgentWorkMemory:
    def __init__(
        self,
        *,
        automation: AutomationService,
        activity: ActivityService,
        auto_distillation: AutoDistillationService,
        auto_distill: AutoDistillWorkflow,
        sessions: SessionsService,
        vault: VaultService,
        collect: CollectAgentRecordsWorkflow,
        curators: CuratorsService,
        diagnostics: DiagnosticsService,
        distill: DistillSessionsWorkflow,
        distill_coordination: DistillCoordination,
        distillation: DistillationService,
        import_records: ImportAgentRecordsWorkflow,
        import_legacy: ImportLegacyAlmanacWorkflow,
        improvement: ImprovementService,
        improvement_proposer: ImprovementProposer,
        improve_harness: ImproveHarnessWorkflow,
        remotes: RemotesService,
        remote_sync: SyncRemoteRecordsWorkflow,
        search: SearchService,
        setup: SetupAgentWorkMemoryWorkflow,
        sync: SyncAgentRecordsWorkflow,
        synchronization: SynchronizationService,
        translations: TranslationService,
        translate: TranslateWikiWorkflow,
        viewer: ViewerService,
        vault_repository: VaultRepositoryWorkflow,
        wiki: WikiCatalogService,
    ):
        self.automation = automation
        self.activity = activity
        self.auto_distillation = auto_distillation
        self.auto_distill = auto_distill
        self.sessions = sessions
        self.vault = vault
        self.collect = collect
        self.curators = curators
        self.diagnostics = diagnostics
        self.distill = distill
        self.distill_coordination = distill_coordination
        self.distillation = distillation
        self.import_records = import_records
        self.import_legacy = import_legacy
        self.improvement = improvement
        self.improvement_proposer = improvement_proposer
        self.improve_harness = improve_harness
        self.remotes = remotes
        self.remote_sync = remote_sync
        self.search = search
        self.setup = setup
        self.sync = sync
        self.synchronization = synchronization
        self.translations = translations
        self.translate = translate
        self.viewer = viewer
        self.vault_repository = vault_repository
        self.wiki = wiki

    @property
    def config(self) -> AgentWorkMemoryConfig:
        return self.vault.config


def create_app(
    config: AgentWorkMemoryConfig | None = None,
    *,
    curator_adapters: Sequence[CuratorAdapter] | None = None,
    scheduler_adapter: SchedulerAdapter | None = None,
    auto_distill_scheduler_adapter: AutoDistillSchedulerAdapter | None = None,
    remote_adapter: RemoteSnapshotAdapter | None = None,
    vault_repository_adapter: VaultRepositoryAdapter | None = None,
    ollama_url: str | None = None,
    improvement_proposer: ImprovementProposer | None = None,
) -> AgentWorkMemory:
    resolved = config or load_config()
    with open_database(resolved.database_path):
        pass
    store = SessionsStore(resolved.database_path)
    sessions = SessionsService(store)
    improvement = ImprovementService(
        ImprovementStore(resolved.state_dir / "improvement")
    )
    improve_harness = ImproveHarnessWorkflow(
        sessions,
        improvement,
        GitRevisionReader(),
        proposer=(
            improvement_proposer
            if improvement_proposer is not None
            else CodexImprovementProposer()
        ),
        proposer_settings=resolved.improvement_proposer,
    )
    vault = VaultService(resolved)
    wiki = WikiCatalogService(vault, sessions)
    collectors = (
        CodexTranscriptCollector(),
        ClaudeTranscriptCollector(),
        CursorTranscriptCollector(),
    )
    collect = CollectAgentRecordsWorkflow(sessions, vault, wiki, collectors)
    remotes = RemotesService(
        RemoteStore(resolved.state_dir / "remotes"),
        remote_adapter or SshRemoteSnapshotAdapter(),
    )
    remote_sync = SyncRemoteRecordsWorkflow(remotes, collect)
    import_records = ImportAgentRecordsWorkflow(sessions, vault, wiki)
    search = SearchService(resolved.database_path, sessions, vault)
    vault_repository_service = VaultRepositoryService(
        vault,
        vault_repository_adapter or GitVaultRepositoryAdapter(),
    )
    vault_repository = VaultRepositoryWorkflow(
        vault_repository_service,
        wiki,
        search,
    )
    import_legacy = ImportLegacyAlmanacWorkflow(vault, wiki, search)
    synchronization = SynchronizationService(
        SynchronizationStore(resolved.database_path)
    )
    activity = ActivityService(
        resolved.state_dir / "activity",
        PsutilActivityProcessProbe(),
    )
    sync = SyncAgentRecordsWorkflow(
        collect,
        remote_sync,
        search,
        synchronization,
        resolved.state_dir / "sync.lock",
    )
    automation = AutomationService(
        scheduler_adapter or default_scheduler_adapter(),
        AutomationStore(resolved.state_dir / "auto-sync.json"),
        resolved.state_dir,
    )
    auto_distillation = AutoDistillationService(
        auto_distill_scheduler_adapter
        or default_auto_distill_scheduler_adapter(),
        AutoDistillStore(resolved.state_dir / "auto-distill.json"),
        resolved.state_dir,
    )
    translations = TranslationService(vault)
    viewer = ViewerService(
        sessions,
        vault,
        wiki,
        synchronization,
        automation,
        auto_distillation,
        translations,
    )
    setup = SetupAgentWorkMemoryWorkflow(vault, wiki, sync, automation)
    adapters = (
        tuple(curator_adapters)
        if curator_adapters is not None
        else (
            YokeCuratorAdapter(
                "codex",
                resolved.state_dir / "curators" / "codex",
                workspace_permission_repair=(
                    vault.normalize_curator_workspace_permissions
                ),
            ),
            YokeCuratorAdapter(
                "claude",
                resolved.state_dir / "curators" / "claude",
                workspace_permission_repair=(
                    vault.normalize_curator_workspace_permissions
                ),
            ),
            OllamaCuratorAdapter(
                ollama_url if ollama_url is not None else "http://127.0.0.1:11434"
            ),
        )
    )
    curators = CuratorsService(adapters)
    diagnostics = DiagnosticsService(
        resolved,
        vault,
        automation,
        auto_distillation,
        curators,
        sessions,
        wiki,
        remotes,
    )
    distillation = DistillationService(DistillationStore(resolved.database_path))
    distill = DistillSessionsWorkflow(
        sessions,
        curators,
        distillation,
        vault,
        search,
        wiki,
    )
    translate = TranslateWikiWorkflow(
        curators,
        vault,
        wiki,
        translations,
    )
    distill_coordination = DistillCoordination(
        resolved.state_dir / "auto-distill.lock",
        resolved.state_dir / "sync.lock",
    )
    auto_distill = AutoDistillWorkflow(
        auto_distillation,
        sessions,
        distill,
        translate,
        distill_coordination,
    )
    return AgentWorkMemory(
        automation=automation,
        activity=activity,
        auto_distillation=auto_distillation,
        auto_distill=auto_distill,
        sessions=sessions,
        vault=vault,
        collect=collect,
        curators=curators,
        diagnostics=diagnostics,
        distill=distill,
        distill_coordination=distill_coordination,
        distillation=distillation,
        import_records=import_records,
        import_legacy=import_legacy,
        improvement=improvement,
        improvement_proposer=improve_harness.proposer,
        improve_harness=improve_harness,
        remotes=remotes,
        remote_sync=remote_sync,
        search=search,
        setup=setup,
        sync=sync,
        synchronization=synchronization,
        translations=translations,
        translate=translate,
        viewer=viewer,
        vault_repository=vault_repository,
        wiki=wiki,
    )
