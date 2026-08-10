import os
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import StringConstraints, field_validator, model_validator

from agentworkmemory.core import AgentWorkMemoryModel
from agentworkmemory.services.curators.models import ContentAccess, ReasoningEffort
from agentworkmemory.services.sessions.models import AgentEventKind

ImprovementIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]


class ImprovementRunState(StrEnum):
    PREPARED = "prepared"
    CANDIDATE_RECORDED = "candidate-recorded"
    QUALIFIED = "qualified"
    REJECTED = "rejected"


class ImprovementProposerPolicy(AgentWorkMemoryModel):
    runtime: Literal["codex"] = "codex"
    model: str
    reasoning_effort: ReasoningEffort

    @field_validator("model")
    @classmethod
    def nonblank_model(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("improvement proposer model must not be blank")
        return model


class ImprovementProposalAttemptState(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class HarnessComponent(StrEnum):
    SYSTEM_PROMPT = "system-prompt"
    TOOL_DESCRIPTION = "tool-description"
    TOOL_IMPLEMENTATION = "tool-implementation"
    MIDDLEWARE = "middleware"
    SKILL = "skill"
    SUBAGENT_CONFIGURATION = "subagent-configuration"
    LONG_TERM_MEMORY = "long-term-memory"


class EvaluationSuite(StrEnum):
    HELD_IN = "held-in"
    HELD_OUT = "held-out"


class CandidateDecision(StrEnum):
    QUALIFIED = "qualified"
    REJECTED = "rejected"


class ImprovementEvidenceEvent(AgentWorkMemoryModel):
    event_id: str
    sequence: int
    kind: AgentEventKind
    role: str | None = None
    label: str
    occurred_at: datetime | None = None
    source_line: int | None = None
    created_at: datetime | None = None
    content: str | None = None

    @field_validator("event_id", "label")
    @classmethod
    def required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("improvement evidence text must not be empty")
        return text

    @field_validator("source_line")
    @classmethod
    def non_negative_source_line(cls, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise ValueError("improvement evidence source line must be non-negative")
        return value

    @field_validator("sequence")
    @classmethod
    def non_negative_sequence(cls, value: int) -> int:
        if value < 0:
            raise ValueError("improvement evidence sequence must be non-negative")
        return value


class ImprovementEvidence(AgentWorkMemoryModel):
    session_id: str
    provider: str
    title: str
    workspace: Path | None = None
    events: tuple[ImprovementEvidenceEvent, ...]

    @field_validator("session_id", "provider", "title")
    @classmethod
    def required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("improvement evidence text must not be empty")
        return text


class ImprovementRunManifest(AgentWorkMemoryModel):
    run_id: ImprovementIdentifier
    repository: Path
    base_revision: str
    content_access: ContentAccess
    editable_paths: tuple[Path, ...]
    state: ImprovementRunState
    created_at: datetime
    updated_at: datetime

    @field_validator("repository")
    @classmethod
    def absolute_repository(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("improvement repository must be absolute")
        return value

    @field_validator("base_revision")
    @classmethod
    def required_revision(cls, value: str) -> str:
        revision = value.strip()
        if not revision:
            raise ValueError("improvement base revision must not be empty")
        return revision

    @field_validator("editable_paths")
    @classmethod
    def valid_editable_paths(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        return normalize_relative_paths(value, "editable")


class ImprovementRun(AgentWorkMemoryModel):
    run_id: ImprovementIdentifier
    repository: Path
    base_revision: str
    content_access: ContentAccess
    editable_paths: tuple[Path, ...]
    evidence: tuple[ImprovementEvidence, ...]
    state: ImprovementRunState
    created_at: datetime
    updated_at: datetime

    @field_validator("repository")
    @classmethod
    def absolute_repository(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("improvement repository must be absolute")
        return value

    @field_validator("base_revision")
    @classmethod
    def required_revision(cls, value: str) -> str:
        revision = value.strip()
        if not revision:
            raise ValueError("improvement base revision must not be empty")
        return revision

    @field_validator("editable_paths")
    @classmethod
    def valid_editable_paths(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        return normalize_relative_paths(value, "editable")

    @field_validator("evidence")
    @classmethod
    def require_evidence(
        cls,
        value: tuple[ImprovementEvidence, ...],
    ) -> tuple[ImprovementEvidence, ...]:
        if not value:
            raise ValueError("improvement run requires at least one evidence selection")
        session_ids = tuple(evidence.session_id for evidence in value)
        if len(set(session_ids)) != len(session_ids):
            raise ValueError("improvement evidence sessions must be unique")
        return value

    def manifest(self) -> ImprovementRunManifest:
        return ImprovementRunManifest(
            run_id=self.run_id,
            repository=self.repository,
            base_revision=self.base_revision,
            content_access=self.content_access,
            editable_paths=self.editable_paths,
            state=self.state,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class ImprovementProposalAttempt(AgentWorkMemoryModel):
    attempt_id: ImprovementIdentifier
    run_id: ImprovementIdentifier
    policy: ImprovementProposerPolicy
    base_revision: str
    worktree: Path
    state: ImprovementProposalAttemptState
    started_at: datetime
    completed_at: datetime | None = None
    candidate_id: ImprovementIdentifier | None = None
    failure: str | None = None

    @field_validator("base_revision")
    @classmethod
    def required_revision(cls, value: str) -> str:
        revision = value.strip()
        if not revision:
            raise ValueError("improvement attempt base revision must not be empty")
        return revision

    @field_validator("worktree")
    @classmethod
    def absolute_worktree(cls, value: Path) -> Path:
        worktree = Path(value).expanduser()
        if not worktree.is_absolute():
            raise ValueError("improvement attempt worktree must be absolute")
        return worktree.resolve(strict=False)

    @field_validator("failure")
    @classmethod
    def valid_failure(cls, value: str | None) -> str | None:
        if value is None:
            return None
        failure = value.strip()
        if not failure:
            raise ValueError("improvement attempt failure must not be blank")
        return failure

    @model_validator(mode="after")
    def valid_lifecycle(self) -> "ImprovementProposalAttempt":
        if self.state is ImprovementProposalAttemptState.STARTED:
            if self.completed_at is not None:
                raise ValueError("started improvement attempt cannot be completed")
            if self.candidate_id is not None or self.failure is not None:
                raise ValueError("started improvement attempt cannot have an outcome")
        elif self.state is ImprovementProposalAttemptState.SUCCEEDED:
            if self.completed_at is None or self.candidate_id is None:
                raise ValueError(
                    "succeeded improvement attempt needs completion and candidate"
                )
            if self.failure is not None:
                raise ValueError("succeeded improvement attempt cannot have a failure")
        else:
            if self.completed_at is None or self.failure is None:
                raise ValueError(
                    "failed improvement attempt needs completion and failure"
                )
            if self.candidate_id is not None:
                raise ValueError("failed improvement attempt cannot have a candidate")
        return self


class ImprovementCandidateProposal(AgentWorkMemoryModel):
    component: HarnessComponent
    failure_evidence: tuple[str, ...]
    root_cause: str
    targeted_fix: str
    predicted_impact: str
    regression_risks: tuple[str, ...] = ()
    changed_paths: tuple[Path, ...]

    @field_validator("failure_evidence")
    @classmethod
    def require_failure_evidence(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        evidence = required_text_sequence(value, "failure evidence")
        if not evidence:
            raise ValueError("improvement candidate needs failure evidence")
        return evidence

    @field_validator("regression_risks")
    @classmethod
    def valid_regression_risks(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        return required_text_sequence(value, "regression risk")

    @field_validator("root_cause", "targeted_fix", "predicted_impact")
    @classmethod
    def required_manifesto_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("improvement candidate manifesto text must not be empty")
        return text

    @field_validator("changed_paths")
    @classmethod
    def valid_changed_paths(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        paths = normalize_relative_paths(value, "changed")
        if not paths:
            raise ValueError("improvement candidate needs at least one changed path")
        return paths


class ImprovementCandidate(ImprovementCandidateProposal):
    candidate_id: ImprovementIdentifier
    run_id: ImprovementIdentifier


class EvaluationCaseResult(AgentWorkMemoryModel):
    suite: EvaluationSuite
    case_id: str
    baseline_passed: bool
    candidate_passed: bool

    @field_validator("case_id")
    @classmethod
    def required_case_id(cls, value: str) -> str:
        case_id = value.strip()
        if not case_id:
            raise ValueError("evaluation case id must not be empty")
        return case_id


def duplicate_evaluation_case_identities(
    cases: tuple[EvaluationCaseResult, ...],
) -> tuple[str, ...]:
    seen: set[tuple[EvaluationSuite, str]] = set()
    duplicates: list[str] = []
    for case in cases:
        identity = (case.suite, case.case_id)
        if identity in seen:
            display_identity = f"{case.suite.value}:{case.case_id}"
            if display_identity not in duplicates:
                duplicates.append(display_identity)
        seen.add(identity)
    return tuple(duplicates)


class EvaluationReport(AgentWorkMemoryModel):
    candidate_id: ImprovementIdentifier
    cases: tuple[EvaluationCaseResult, ...]
    decision: CandidateDecision
    reasons: tuple[str, ...] = ()

    @field_validator("reasons")
    @classmethod
    def valid_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return required_text_sequence(value, "evaluation reason")


def required_text_sequence(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    cleaned = tuple(value.strip() for value in values)
    if any(not value for value in cleaned):
        raise ValueError(f"{label} must not be empty")
    return cleaned


def normalize_relative_path(value: Path) -> Path:
    path = Path(value)
    if path.is_absolute() or path.root or path.drive:
        raise ValueError(f"{path} must be a relative path")
    if any(part == ".." for part in path.parts):
        raise ValueError(f"{path} must not escape its prepared surface")
    parts = tuple(part for part in path.parts if part not in ("", "."))
    return Path(*parts) if parts else Path(".")


def normalize_relative_paths(
    values: tuple[Path, ...],
    label: str,
) -> tuple[Path, ...]:
    normalized = tuple(normalize_relative_path(value) for value in values)
    if not normalized and label == "editable":
        raise ValueError("editable paths must not be empty")
    keys = tuple(os.path.normcase(str(path)) for path in normalized)
    if len(set(keys)) != len(keys):
        raise ValueError(f"{label} paths must not contain duplicates")
    return normalized


def paths_inside_surface(
    changed_paths: tuple[Path, ...],
    editable_paths: tuple[Path, ...],
) -> bool:
    normalized_changed = normalize_relative_paths(changed_paths, "changed")
    normalized_editable = normalize_relative_paths(editable_paths, "editable")
    return all(
        any(
            changed == editable or changed.is_relative_to(editable)
            for editable in normalized_editable
        )
        for changed in normalized_changed
    )


def require_paths_inside_surface(
    changed_paths: tuple[Path, ...],
    editable_paths: tuple[Path, ...],
) -> None:
    if not paths_inside_surface(changed_paths, editable_paths):
        changed = ", ".join(path.as_posix() for path in changed_paths)
        editable = ", ".join(path.as_posix() for path in editable_paths)
        raise ValueError(
            "improvement candidate changed paths must stay inside the prepared "
            f"editable surface (changed: {changed}; editable: {editable})"
        )
