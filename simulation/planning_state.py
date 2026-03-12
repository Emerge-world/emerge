from dataclasses import dataclass, field


@dataclass
class PlanningSubgoal:
    description: str
    kind: str
    target: str | None = None
    preconditions: list[str] = field(default_factory=list)
    completion_signal: str = ""
    failure_signal: str = ""
    priority: int = 1


@dataclass
class PlanningState:
    goal: str
    goal_type: str
    subgoals: list[PlanningSubgoal]
    active_subgoal_index: int
    status: str
    created_tick: int
    last_plan_tick: int
    last_progress_tick: int
    confidence: float
    horizon: str
    success_signals: list[str] = field(default_factory=list)
    abort_conditions: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    rationale_summary: str = ""

    @classmethod
    def empty(cls) -> "PlanningState":
        return cls(
            goal="",
            goal_type="",
            subgoals=[],
            active_subgoal_index=0,
            status="empty",
            created_tick=0,
            last_plan_tick=0,
            last_progress_tick=0,
            confidence=0.0,
            horizon="short",
        )

    def needs_replan(self, tick: int, plan_refresh_interval: int) -> bool:
        if self.status in {"empty", "blocked", "completed", "abandoned", "stale"}:
            return True
        return (tick - self.last_plan_tick) >= plan_refresh_interval
