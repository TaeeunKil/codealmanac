from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

from agentworkmemory.services.search.service import SearchService
from agentworkmemory.services.vault_repository.models import (
    VaultRepositoryResult,
    VaultRepositoryStatus,
)
from agentworkmemory.services.vault_repository.service import VaultRepositoryService
from agentworkmemory.services.wiki.service import WikiCatalogService

DEFAULT_VAULT_SYNC_WAIT_SECONDS = 10 * 60


class VaultSynchronizationWaitExpired(RuntimeError):
    """Raised when Vault Git work cannot wait for transcript sync to finish."""


class VaultRepositoryWorkflow:
    def __init__(
        self,
        repository: VaultRepositoryService,
        wiki: WikiCatalogService,
        search: SearchService,
        sync_lock_path: Path,
        sync_wait_seconds: float = DEFAULT_VAULT_SYNC_WAIT_SECONDS,
    ):
        self.repository = repository
        self.wiki = wiki
        self.search = search
        self.sync_lock_path = sync_lock_path
        self.sync_wait_seconds = sync_wait_seconds

    def connect(self, repository: str, destination: Path) -> Path:
        path = self.repository.connect(repository, destination)
        self.refresh_local_views()
        return path

    def publish(self, repository: str) -> VaultRepositoryResult:
        with vault_synchronization_lock(
            self.sync_lock_path,
            wait_seconds=self.sync_wait_seconds,
        ):
            self.refresh_local_views()
            return self.repository.publish(repository)

    def status(self) -> VaultRepositoryStatus:
        return self.repository.status()

    def pull(self) -> VaultRepositoryResult:
        with vault_synchronization_lock(
            self.sync_lock_path,
            wait_seconds=self.sync_wait_seconds,
        ):
            result = self.repository.pull()
            self.refresh_local_views()
            return result

    def push(self, message: str) -> VaultRepositoryResult:
        with vault_synchronization_lock(
            self.sync_lock_path,
            wait_seconds=self.sync_wait_seconds,
        ):
            self.refresh_local_views()
            return self.repository.push(message)

    def sync(self, message: str) -> VaultRepositoryResult:
        with vault_synchronization_lock(
            self.sync_lock_path,
            wait_seconds=self.sync_wait_seconds,
        ):
            self.refresh_local_views()
            result = self.repository.sync(message)
            self.refresh_local_views()
            follow_up = self.repository.push(message)
            if follow_up.committed:
                result = follow_up
            return result

    def refresh_local_views(self) -> None:
        self.wiki.refresh()
        self.search.refresh()


@contextmanager
def vault_synchronization_lock(
    path: Path,
    *,
    wait_seconds: float,
) -> Iterator[None]:
    try:
        with FileLock(path, timeout=wait_seconds):
            yield
    except Timeout as error:
        raise VaultSynchronizationWaitExpired(
            "Vault synchronization waited for transcript sync to finish "
            f"for {wait_seconds:g} second(s)."
        ) from error
