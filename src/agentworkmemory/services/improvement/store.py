import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from pydantic import TypeAdapter

from agentworkmemory.services.curators.models import ContentAccess
from agentworkmemory.services.improvement.models import (
    CandidateDecision,
    EvaluationReport,
    ImprovementCandidate,
    ImprovementEvidence,
    ImprovementProposalAttempt,
    ImprovementProposalAttemptState,
    ImprovementRun,
    ImprovementRunManifest,
    duplicate_evaluation_case_identities,
    require_paths_inside_surface,
)

SAFE_STORE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ImprovementStore:
    """Persist improvement runs only below one canonical improvement root."""

    def __init__(self, root: Path):
        resolved = Path(root).expanduser().resolve(strict=False)
        if not resolved.is_absolute():
            raise ValueError("improvement store root must be absolute")
        self.root = resolved

    def save_run(self, run: ImprovementRun) -> None:
        self.validate_run_location(run)
        run_root = self.run_directory(run.run_id)
        if run_root.exists():
            raise FileExistsError(f"improvement run already exists: {run.run_id}")
        if run.content_access is ContentAccess.METADATA_ONLY and evidence_has_content(
            run.evidence
        ):
            raise ValueError(
                "metadata-only improvement evidence must not contain bodies"
            )

        runs_root = self.root / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".run-", dir=runs_root))
        try:
            atomic_write_text(
                staging / "manifest.json",
                run.manifest().model_dump_json(indent=2) + "\n",
                self.root,
            )
            evidence_payload = json.dumps(
                tuple(
                    evidence.model_dump(mode="json", exclude_none=True)
                    for evidence in run.evidence
                ),
                indent=2,
                ensure_ascii=False,
            )
            atomic_write_text(
                staging / "evidence.json",
                evidence_payload + "\n",
                self.root,
            )
            publish_directory(staging, run_root, self.root)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def update_run(self, run: ImprovementRun) -> None:
        self.validate_run_location(run)
        current = self.get_run(run.run_id)
        if current is None:
            raise KeyError(f"unknown improvement run: {run.run_id}")
        immutable_fields = (
            ("repository", current.repository, run.repository),
            ("base_revision", current.base_revision, run.base_revision),
            ("content_access", current.content_access, run.content_access),
            ("editable_paths", current.editable_paths, run.editable_paths),
            ("evidence", current.evidence, run.evidence),
            ("created_at", current.created_at, run.created_at),
        )
        for field_name, current_value, updated_value in immutable_fields:
            if current_value != updated_value:
                raise ValueError(
                    f"improvement run {field_name} is immutable"
                )
        atomic_write_text(
            self.run_directory(run.run_id) / "manifest.json",
            run.manifest().model_dump_json(indent=2) + "\n",
            self.root,
        )

    def get_run(self, run_id: str) -> ImprovementRun | None:
        run_root = self.run_directory(run_id)
        manifest_path = run_root / "manifest.json"
        evidence_path = run_root / "evidence.json"
        if not manifest_path.is_file() or not evidence_path.is_file():
            return None
        manifest = ImprovementRunManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        evidence = TypeAdapter(tuple[ImprovementEvidence, ...]).validate_json(
            evidence_path.read_text(encoding="utf-8")
        )
        return ImprovementRun(
            run_id=manifest.run_id,
            repository=manifest.repository,
            base_revision=manifest.base_revision,
            content_access=manifest.content_access,
            editable_paths=manifest.editable_paths,
            evidence=evidence,
            state=manifest.state,
            created_at=manifest.created_at,
            updated_at=manifest.updated_at,
        )

    def list_runs(self) -> tuple[ImprovementRun, ...]:
        runs_root = self.root / "runs"
        if not runs_root.is_dir():
            return ()
        runs: list[ImprovementRun] = []
        for path in runs_root.iterdir():
            if not path.is_dir() or path.name.startswith("."):
                continue
            run = self.get_run(path.name)
            if run is not None:
                runs.append(run)
        return tuple(
            sorted(runs, key=lambda run: (run.created_at, run.run_id), reverse=True)
        )

    def save_attempt(self, attempt: ImprovementProposalAttempt) -> None:
        self.validate_attempt_location(attempt)
        if self.get_run(attempt.run_id) is None:
            raise KeyError(f"unknown improvement run: {attempt.run_id}")
        attempt_root = self.attempt_directory(attempt.run_id, attempt.attempt_id)
        if attempt_root.exists():
            raise FileExistsError(
                f"improvement attempt already exists: {attempt.attempt_id}"
            )
        attempts_root = self.run_directory(attempt.run_id) / "attempts"
        attempts_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".attempt-", dir=attempts_root))
        try:
            atomic_write_text(
                staging / "manifest.json",
                attempt.model_dump_json(indent=2) + "\n",
                self.root,
            )
            publish_directory(staging, attempt_root, self.root)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def update_attempt(self, attempt: ImprovementProposalAttempt) -> None:
        self.validate_attempt_location(attempt)
        current = self.get_attempt(attempt.run_id, attempt.attempt_id)
        if current is None:
            raise KeyError(f"unknown improvement attempt: {attempt.attempt_id}")
        immutable_fields = (
            ("run_id", current.run_id, attempt.run_id),
            ("policy", current.policy, attempt.policy),
            ("base_revision", current.base_revision, attempt.base_revision),
            ("worktree", current.worktree, attempt.worktree),
            ("started_at", current.started_at, attempt.started_at),
        )
        for field_name, current_value, updated_value in immutable_fields:
            if current_value != updated_value:
                raise ValueError(f"improvement attempt {field_name} is immutable")
        if current.state is not ImprovementProposalAttemptState.STARTED:
            raise ValueError("improvement attempt is already terminal")
        if attempt.state is ImprovementProposalAttemptState.STARTED:
            raise ValueError("improvement attempt update needs a terminal state")
        atomic_write_text(
            self.attempt_directory(attempt.run_id, attempt.attempt_id)
            / "manifest.json",
            attempt.model_dump_json(indent=2) + "\n",
            self.root,
        )

    def get_attempt(
        self,
        run_id: str,
        attempt_id: str,
    ) -> ImprovementProposalAttempt | None:
        manifest_path = (
            self.attempt_directory(run_id, attempt_id) / "manifest.json"
        )
        if not manifest_path.is_file():
            return None
        return ImprovementProposalAttempt.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )

    def list_attempts(
        self,
        run_id: str,
    ) -> tuple[ImprovementProposalAttempt, ...]:
        attempts_root = self.run_directory(run_id) / "attempts"
        if not attempts_root.is_dir():
            return ()
        attempts: list[ImprovementProposalAttempt] = []
        for path in attempts_root.iterdir():
            if not path.is_dir() or path.name.startswith("."):
                continue
            attempt = self.get_attempt(run_id, path.name)
            if attempt is not None:
                attempts.append(attempt)
        return tuple(
            sorted(
                attempts,
                key=lambda attempt: (attempt.started_at, attempt.attempt_id),
            )
        )

    def find_attempt(self, attempt_id: str) -> ImprovementProposalAttempt | None:
        for run in self.list_runs():
            attempt = self.get_attempt(run.run_id, attempt_id)
            if attempt is not None:
                return attempt
        return None

    def save_candidate(
        self,
        run: ImprovementRun,
        candidate: ImprovementCandidate,
    ) -> None:
        self.validate_run_location(run)
        if candidate.run_id != run.run_id:
            raise ValueError("improvement candidate belongs to a different run")
        require_paths_inside_surface(candidate.changed_paths, run.editable_paths)
        run_root = self.run_directory(run.run_id)
        if not run_root.is_dir():
            raise KeyError(f"unknown improvement run: {run.run_id}")
        candidate_root = self.candidate_directory(run.run_id, candidate.candidate_id)
        if candidate_root.exists():
            raise FileExistsError(
                f"improvement candidate already exists: {candidate.candidate_id}"
            )
        candidates_root = run_root / "candidates"
        candidates_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".candidate-", dir=candidates_root))
        try:
            atomic_write_text(
                staging / "manifest.json",
                candidate.model_dump_json(indent=2) + "\n",
                self.root,
            )
            publish_directory(staging, candidate_root, self.root)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def get_candidate(
        self,
        run_id: str,
        candidate_id: str,
    ) -> ImprovementCandidate | None:
        manifest_path = self.candidate_directory(run_id, candidate_id) / "manifest.json"
        if not manifest_path.is_file():
            return None
        return ImprovementCandidate.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )

    def list_candidates(self, run_id: str) -> tuple[ImprovementCandidate, ...]:
        candidates_root = self.run_directory(run_id) / "candidates"
        if not candidates_root.is_dir():
            return ()
        candidates: list[ImprovementCandidate] = []
        for path in candidates_root.iterdir():
            if not path.is_dir() or path.name.startswith("."):
                continue
            candidate = self.get_candidate(run_id, path.name)
            if candidate is not None:
                candidates.append(candidate)
        return tuple(sorted(candidates, key=lambda candidate: candidate.candidate_id))

    def save_evaluation(
        self,
        run_id: str,
        candidate_id: str,
        report: EvaluationReport,
    ) -> None:
        if report.candidate_id != candidate_id:
            raise ValueError("evaluation report belongs to a different candidate")
        duplicate_identities = duplicate_evaluation_case_identities(report.cases)
        if report.decision is CandidateDecision.QUALIFIED and duplicate_identities:
            identities = ", ".join(duplicate_identities)
            raise ValueError(
                "qualified evaluation report cannot contain duplicate "
                f"case identities: {identities}"
            )
        candidate_root = self.candidate_directory(run_id, candidate_id)
        if not candidate_root.is_dir():
            raise KeyError(f"unknown improvement candidate: {candidate_id}")
        atomic_write_text(
            candidate_root / "evaluation.json",
            report.model_dump_json(indent=2) + "\n",
            self.root,
        )

    def get_evaluation(
        self,
        run_id: str,
        candidate_id: str,
    ) -> EvaluationReport | None:
        evaluation_path = (
            self.candidate_directory(run_id, candidate_id) / "evaluation.json"
        )
        if not evaluation_path.is_file():
            return None
        return EvaluationReport.model_validate_json(
            evaluation_path.read_text(encoding="utf-8")
        )

    def run_directory(self, run_id: str) -> Path:
        return self.safe_child(self.root / "runs" / store_identifier(run_id))

    def candidate_directory(self, run_id: str, candidate_id: str) -> Path:
        return self.safe_child(
            self.run_directory(run_id) / "candidates" / store_identifier(candidate_id)
        )

    def attempt_directory(self, run_id: str, attempt_id: str) -> Path:
        return self.safe_child(
            self.run_directory(run_id) / "attempts" / store_identifier(attempt_id)
        )

    def worktree_directory(self, run_id: str, attempt_id: str) -> Path:
        return self.safe_child(
            self.root / "worktrees" / store_identifier(run_id) / store_identifier(
                attempt_id
            )
        )

    def validate_run_location(self, run: ImprovementRun) -> None:
        self.run_directory(run.run_id)

    def validate_attempt_location(
        self,
        attempt: ImprovementProposalAttempt,
    ) -> None:
        expected_worktree = self.worktree_directory(
            attempt.run_id,
            attempt.attempt_id,
        )
        if attempt.worktree != expected_worktree:
            raise ValueError("improvement attempt worktree is outside the store root")

    def safe_child(self, path: Path) -> Path:
        resolved = path.resolve(strict=False)
        if not resolved.is_relative_to(self.root):
            raise ValueError("improvement persistence path escaped the store root")
        return resolved


def store_identifier(value: str) -> str:
    if not SAFE_STORE_IDENTIFIER.fullmatch(value):
        raise ValueError("improvement persistence identifiers must be safe path names")
    return value


def evidence_has_content(evidence: tuple[ImprovementEvidence, ...]) -> bool:
    return any(
        event.content is not None
        for selection in evidence
        for event in selection.events
    )


def atomic_write_text(path: Path, content: str, root: Path) -> None:
    target = path.resolve(strict=False)
    if not target.is_relative_to(root.resolve(strict=False)):
        raise ValueError("atomic improvement write escaped the store root")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def publish_directory(staging: Path, target: Path, root: Path) -> None:
    safe_staging = staging.resolve(strict=False)
    safe_target = target.resolve(strict=False)
    safe_root = root.resolve(strict=False)
    if not safe_staging.is_relative_to(safe_root):
        raise ValueError("improvement staging path escaped the store root")
    if not safe_target.is_relative_to(safe_root):
        raise ValueError("improvement target path escaped the store root")
    if safe_target.exists():
        raise FileExistsError(f"improvement target already exists: {safe_target.name}")
    os.replace(safe_staging, safe_target)
