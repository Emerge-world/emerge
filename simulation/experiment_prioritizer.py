def rank_candidates(candidates: list[dict]) -> list[dict]:
    def score(candidate: dict) -> float:
        return round(
            candidate.get("uncertainty", 0.0)
            + candidate.get("upside", 0.0)
            + candidate.get("strategic_value", 0.0),
            4,
        )

    ranked = [{**candidate, "priority_score": score(candidate)} for candidate in candidates]
    return sorted(ranked, key=lambda item: item["priority_score"], reverse=True)
