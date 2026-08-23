import subprocess
from pathlib import Path

import pytest
from filelock import FileLock

from agentworkmemory.app import create_app
from agentworkmemory.cli import build_parser, dispatch
from agentworkmemory.integrations.vault_repository import (
    GitVaultRepositoryAdapter,
)
from agentworkmemory.services.vault_repository import VaultRepositoryStatus
from agentworkmemory.settings import AgentWorkMemoryConfig


class FakeVaultRepositoryAdapter:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []
        self.clean = True

    def clone(self, repository: str, destination: Path) -> None:
        self.calls.append(("clone", (repository, destination)))
        (destination / ".git").mkdir(parents=True)
        project = destination / "projects" / "portable-memory.md"
        project.parent.mkdir(parents=True)
        project.write_text("# Portable memory\n\nCarried between machines.\n")

    def initialize(self, root: Path, repository: str) -> None:
        self.calls.append(("initialize", (root, repository)))
        (root / ".git").mkdir()

    def status(self, root: Path) -> VaultRepositoryStatus:
        self.calls.append(("status", root))
        return VaultRepositoryStatus(
            path=root,
            branch="main",
            remote="git@example.test:memory.git",
            clean=self.clean,
            changes=0 if self.clean else 1,
        )

    def commit_all(self, root: Path, message: str) -> bool:
        self.calls.append(("commit_all", (root, message)))
        self.clean = True
        return True

    def pull_rebase(self, root: Path) -> None:
        self.calls.append(("pull_rebase", root))

    def push(self, root: Path) -> None:
        self.calls.append(("push", root))


def test_connect_configures_cloned_vault_and_refreshes_search(tmp_path: Path):
    adapter = FakeVaultRepositoryAdapter()
    app = repository_app(tmp_path, adapter)
    destination = tmp_path / "portable-vault"

    connected = app.vault_repository.connect(
        "git@example.test:memory.git",
        destination,
    )

    assert connected == destination.resolve()
    assert app.config.vault_path == destination.resolve()
    assert (destination / "Home.md").is_file()
    assert any(
        result.identity == "projects/portable-memory.md"
        for result in app.search.find("Carried between machines")
    )


def test_publish_and_sync_record_every_vault_change(tmp_path: Path):
    adapter = FakeVaultRepositoryAdapter()
    app = repository_app(tmp_path, adapter)
    vault = app.vault.initialize(tmp_path / "vault")
    (vault / "projects" / "one.md").write_text("# One\n")

    published = app.vault_repository.publish("git@example.test:memory.git")
    (vault / "projects" / "two.md").write_text("# Two\n")
    synced = app.vault_repository.sync("Remember everything")

    assert published.committed
    assert synced.committed
    assert (vault / ".gitignore").is_file()
    assert ("initialize", (vault, "git@example.test:memory.git")) in adapter.calls
    assert ("commit_all", (vault, "Initialize Agent Work Memory Vault")) in (
        adapter.calls
    )
    assert ("commit_all", (vault, "Remember everything")) in adapter.calls
    assert adapter.calls[-5:] == [
        ("commit_all", (vault, "Remember everything")),
        ("pull_rebase", vault),
        ("push", vault),
        ("commit_all", (vault, "Remember everything")),
        ("push", vault),
    ]


def test_vault_cli_status_and_sync(tmp_path: Path, capsys):
    adapter = FakeVaultRepositoryAdapter()
    app = repository_app(tmp_path, adapter)
    app.vault.initialize(tmp_path / "vault")
    (tmp_path / "vault" / ".git").mkdir()

    status_args = build_parser().parse_args(("vault", "status"))
    sync_args = build_parser().parse_args(
        ("vault", "sync", "--message", "Portable update")
    )

    assert dispatch(status_args, app) == 0
    assert dispatch(sync_args, app) == 0

    output = capsys.readouterr().out
    assert "branch: main" in output
    assert "worktree: clean" in output
    assert "Committed, pulled, and pushed" in output


def test_vault_sync_waits_for_transcript_sync_lock(tmp_path: Path):
    adapter = FakeVaultRepositoryAdapter()
    app = repository_app(tmp_path, adapter)
    vault = app.vault.initialize(tmp_path / "vault")
    app.vault_repository.sync_wait_seconds = 0

    with (
        FileLock(tmp_path / "state" / "sync.lock"),
        pytest.raises(RuntimeError, match="waited for transcript sync"),
    ):
        app.vault_repository.sync("Do not race sync")

    assert not any(
        call[0] in {"commit_all", "pull_rebase", "push"}
        for call in adapter.calls
    )
    assert vault.is_dir()


def test_vault_push_refuses_an_oversized_file_before_staging(
    tmp_path: Path,
    monkeypatch,
):
    adapter = FakeVaultRepositoryAdapter()
    app = repository_app(tmp_path, adapter)
    vault = app.vault.initialize(tmp_path / "vault")
    (vault / "inbox" / "agent-sessions" / "oversized.md").write_bytes(b"x" * 101)
    monkeypatch.setattr(
        "agentworkmemory.services.vault_repository.service.MAX_PUBLISHABLE_FILE_BYTES",
        100,
    )

    with pytest.raises(ValueError, match="publication limit"):
        app.vault_repository.push("Publish safely")

    assert not any(call[0] == "commit_all" for call in adapter.calls)


def test_setup_can_clone_private_vault_repository(tmp_path: Path, capsys):
    adapter = FakeVaultRepositoryAdapter()
    app = repository_app(tmp_path, adapter)
    destination = tmp_path / "vault"
    args = build_parser().parse_args(
        (
            "setup",
            str(destination),
            "--vault-repo",
            "git@example.test:memory.git",
            "--home",
            str(tmp_path / "empty-home"),
            "--from",
            "codex",
        )
    )

    assert dispatch(args, app) == 0

    assert adapter.calls[0] == (
        "clone",
        ("git@example.test:memory.git", destination.resolve()),
    )
    assert app.config.vault_path == destination.resolve()
    assert "Agent Work Memory ready" in capsys.readouterr().out


def test_git_adapter_publishes_and_clones_local_repository(
    tmp_path: Path,
    monkeypatch,
):
    configure_git_identity(monkeypatch)
    remote = tmp_path / "memory.git"
    subprocess.run(("git", "init", "--bare", str(remote)), check=True)
    root = tmp_path / "vault"
    root.mkdir()
    (root / "Home.md").write_text("# Home\n")
    adapter = GitVaultRepositoryAdapter("git")

    adapter.initialize(root, str(remote))
    adapter.initialize(root, str(remote))
    with pytest.raises(ValueError, match="does not match"):
        adapter.initialize(root, str(tmp_path / "different.git"))
    assert adapter.commit_all(root, "Initialize memory")
    adapter.push(root)
    subprocess.run(
        ("git", "-C", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"),
        check=True,
    )

    status = adapter.status(root)
    assert status.branch == "main"
    assert status.clean
    clone = tmp_path / "clone"
    adapter.clone(str(remote), clone)
    assert (clone / "Home.md").read_text() == "# Home\n"


def repository_app(tmp_path: Path, adapter: FakeVaultRepositoryAdapter):
    return create_app(
        AgentWorkMemoryConfig(state_dir=tmp_path / "state"),
        vault_repository_adapter=adapter,
    )


def configure_git_identity(monkeypatch) -> None:
    monkeypatch.setenv("GIT_AUTHOR_NAME", "AWM Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "awm@example.test")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "AWM Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "awm@example.test")
