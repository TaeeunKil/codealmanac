import re
import shutil
import subprocess
from pathlib import Path

from agentworkmemory.integrations.processes import hidden_process_creation_flags

COMMAND_TIMEOUT_SECONDS = 10
MAX_OUTPUT_BYTES = 4096
URL_CREDENTIALS = re.compile(r"(?i)(https?://)([^/\s@]+)@")


class GitRevisionReader:
    """Read one repository HEAD revision without mutating the checkout."""

    def __init__(self, executable: str | None = None):
        self.executable = executable or shutil.which("git")

    def head(self, repository: Path) -> str:
        if not repository.is_absolute():
            raise ValueError("Git revision lookup requires an absolute repository")
        if self.executable is None:
            raise RuntimeError("Git executable was not found")
        try:
            completed = subprocess.run(
                (self.executable, "rev-parse", "HEAD"),
                cwd=repository,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
                creationflags=hidden_process_creation_flags(),
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Git revision lookup timed out") from error
        except OSError as error:
            raise RuntimeError("Git revision lookup could not start") from error
        except subprocess.CalledProcessError as error:
            detail = sanitized_process_output(error.stderr or error.stdout)
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"Git revision lookup failed{suffix}") from error

        revision = sanitized_process_output(completed.stdout)
        if not revision or "\n" in revision or "\r" in revision:
            raise RuntimeError("Git revision lookup returned an invalid revision")
        return revision


class GitWorktreeManager:
    """Create and inspect detached candidate worktrees with bounded Git calls."""

    def __init__(self, executable: str | None = None):
        self.executable = executable or shutil.which("git")

    def create_detached(
        self,
        repository: Path,
        worktree: Path,
        base_revision: str,
    ) -> Path:
        repository = require_absolute_path(repository, "repository")
        worktree = require_absolute_path(worktree, "worktree")
        if worktree.exists() or worktree.is_symlink():
            raise FileExistsError(f"improvement worktree already exists: {worktree}")
        repository_root = repository.resolve(strict=False)
        worktree_root = worktree.resolve(strict=False)
        if worktree_root == repository_root or worktree_root.is_relative_to(
            repository_root
        ):
            raise ValueError("improvement worktree must stay outside the repository")
        if repository_root.is_relative_to(worktree_root):
            raise ValueError("improvement worktree cannot contain the repository")
        if self.executable is None:
            raise RuntimeError("Git executable was not found")
        worktree.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                (
                    self.executable,
                    "worktree",
                    "add",
                    "--detach",
                    str(worktree),
                    base_revision,
                ),
                cwd=repository,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
                creationflags=hidden_process_creation_flags(),
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Git worktree creation timed out") from error
        except OSError as error:
            raise RuntimeError("Git worktree creation could not start") from error
        except subprocess.CalledProcessError as error:
            detail = sanitized_process_output(error.stderr or error.stdout)
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"Git worktree creation failed{suffix}") from error

        self.verify_detached_at(worktree, base_revision)
        return worktree

    def verify_detached_at(self, worktree: Path, base_revision: str) -> None:
        worktree = require_absolute_path(worktree, "worktree")
        actual_revision = GitRevisionReader(self.executable).head(worktree)
        if actual_revision != base_revision:
            raise RuntimeError("Git worktree moved from the prepared revision")
        if self.executable is None:
            raise RuntimeError("Git executable was not found")
        try:
            symbolic_head = subprocess.run(
                (self.executable, "symbolic-ref", "--quiet", "HEAD"),
                cwd=worktree,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                timeout=COMMAND_TIMEOUT_SECONDS,
                creationflags=hidden_process_creation_flags(),
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Git detached-head inspection timed out") from error
        except OSError as error:
            raise RuntimeError(
                "Git detached-head inspection could not start"
            ) from error
        if symbolic_head.returncode == 0:
            raise RuntimeError("Git candidate worktree is attached to a branch")
        if symbolic_head.returncode != 1:
            detail = sanitized_process_output(
                symbolic_head.stderr or symbolic_head.stdout
            )
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"Git detached-head inspection failed{suffix}")

    def changed_paths(self, worktree: Path) -> tuple[Path, ...]:
        worktree = require_absolute_path(worktree, "worktree")
        if self.executable is None:
            raise RuntimeError("Git executable was not found")
        try:
            completed = subprocess.run(
                (
                    self.executable,
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=all",
                    "--no-renames",
                    "-z",
                ),
                cwd=worktree,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
                creationflags=hidden_process_creation_flags(),
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Git changed-path inspection timed out") from error
        except OSError as error:
            raise RuntimeError("Git changed-path inspection could not start") from error
        except subprocess.CalledProcessError as error:
            detail = sanitized_process_output(error.stderr or error.stdout)
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"Git changed-path inspection failed{suffix}") from error

        raw_output = completed.stdout
        if isinstance(raw_output, str):
            raw_paths = raw_output.encode("utf-8")
        else:
            raw_paths = raw_output
        paths: list[Path] = []
        for record in raw_paths.split(b"\0"):
            if not record:
                continue
            if len(record) < 4:
                raise RuntimeError("Git returned an invalid changed-path record")
            status = record[:2].decode("ascii", errors="replace")
            if status == "!!":
                continue
            if record[2:3] != b" ":
                raise RuntimeError("Git returned an invalid changed-path record")
            path_text = record[3:].decode("utf-8", errors="surrogateescape")
            path = Path(path_text)
            if not path_text or path.is_absolute() or ".." in path.parts:
                raise RuntimeError("Git returned a changed path outside the worktree")
            paths.append(path)
        return tuple(paths)


def require_absolute_path(value: Path, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"Git {label} must be absolute")
    return path.resolve(strict=False)


def sanitized_process_output(content: bytes | str) -> str:
    if isinstance(content, bytes):
        decoded = content[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    else:
        decoded = content[:MAX_OUTPUT_BYTES]
    sanitized = URL_CREDENTIALS.sub(r"\1***@", decoded).strip()
    if len(sanitized) > MAX_OUTPUT_BYTES:
        return sanitized[:MAX_OUTPUT_BYTES]
    return sanitized
