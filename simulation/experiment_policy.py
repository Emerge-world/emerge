from dataclasses import dataclass, field


@dataclass
class CandidateDecision:
    decision: str
    reason: str
    rules_fired: list[str] = field(default_factory=list)


def evaluate_candidate(
    comparison: dict,
    candidate_invalid_run_rate: float,
    primary_metrics: list[str],
    tolerances: dict,
    max_invalid_run_rate: float,
    min_effect_size: float,
) -> CandidateDecision:
    if candidate_invalid_run_rate > max_invalid_run_rate:
        return CandidateDecision(
            decision="inconclusive",
            reason="too many invalid runs",
            rules_fired=["invalid_runs"],
        )

    for metric in primary_metrics:
        delta = comparison.get(metric, {}).get("delta", 0.0)
        if delta < tolerances.get(metric, 0.0):
            return CandidateDecision(
                decision="reject",
                reason=f"{metric} regressed",
                rules_fired=["primary_regression"],
            )

    if any(item.get("delta", 0.0) >= min_effect_size for item in comparison.values()):
        return CandidateDecision(
            decision="promote",
            reason="candidate improved without violating gates",
            rules_fired=["value_gain"],
        )

    return CandidateDecision(
        decision="inconclusive",
        reason="effect too small",
        rules_fired=["small_effect"],
    )
