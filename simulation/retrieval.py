from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalContext:
    hunger: int
    energy: int
    life: int
    visible_resources: set[str]
    inventory_items: set[str]
    current_goal: str
    current_subgoal: str
    blockers: tuple[str, ...]


def _score_entry(entry: str, context: RetrievalContext) -> int:
    text = entry.lower()
    score = 0

    if context.hunger >= 80 and "hunger" in text:
        score += 5
    if any(resource in text for resource in context.visible_resources):
        score += 4
    if context.current_goal and any(word in text for word in context.current_goal.lower().split()):
        score += 3
    if any(blocker.lower() in text for blocker in context.blockers):
        score += 2

    return score


def rank_memory_entries(
    semantic: list[str],
    episodic: list[str],
    task: list[str],
    context: RetrievalContext,
    limit: int,
) -> list[str]:
    combined = semantic + episodic + task
    ranked = sorted(combined, key=lambda entry: _score_entry(entry, context), reverse=True)
    return ranked[:limit]
