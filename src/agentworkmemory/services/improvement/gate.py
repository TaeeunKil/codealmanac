from agentworkmemory.services.improvement.models import (
    CandidateDecision,
    EvaluationCaseResult,
    EvaluationReport,
    EvaluationSuite,
    ImprovementIdentifier,
    duplicate_evaluation_case_identities,
)


class AcceptanceGate:
    """Apply the fixed held-in and held-out candidate acceptance policy."""

    def evaluate(
        self,
        candidate_id: ImprovementIdentifier,
        cases: tuple[EvaluationCaseResult, ...],
    ) -> EvaluationReport:
        reasons: list[str] = []
        reasons.extend(
            f"duplicate evaluation case identity: {identity}"
            for identity in duplicate_evaluation_case_identities(cases)
        )
        held_in = tuple(case for case in cases if case.suite is EvaluationSuite.HELD_IN)
        held_out = tuple(
            case for case in cases if case.suite is EvaluationSuite.HELD_OUT
        )

        if not held_in:
            reasons.append("held-in evaluation suite is required")
        if not held_out:
            reasons.append("held-out evaluation suite is required")

        held_in_regressions = tuple(
            case
            for case in held_in
            if case.baseline_passed and not case.candidate_passed
        )
        held_out_regressions = tuple(
            case
            for case in held_out
            if case.baseline_passed and not case.candidate_passed
        )
        if held_in_regressions:
            reasons.extend(
                f"held-in regression: {case.case_id} changed from passing to failing"
                for case in held_in_regressions
            )
        if held_out_regressions:
            reasons.extend(
                f"held-out regression: {case.case_id} changed from passing to failing"
                for case in held_out_regressions
            )

        demonstrated_fix = any(
            not case.baseline_passed and case.candidate_passed for case in held_in
        )
        if held_in and not demonstrated_fix:
            reasons.append(
                "at least one held-in case must change from failing to passing"
            )

        decision = (
            CandidateDecision.REJECTED if reasons else CandidateDecision.QUALIFIED
        )
        return EvaluationReport(
            candidate_id=candidate_id,
            cases=cases,
            decision=decision,
            reasons=tuple(reasons),
        )


def acceptance_gate(
    candidate_id: ImprovementIdentifier,
    cases: tuple[EvaluationCaseResult, ...],
) -> EvaluationReport:
    return AcceptanceGate().evaluate(candidate_id, cases)
