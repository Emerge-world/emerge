from unittest.mock import MagicMock

from simulation.planner import Planner
from simulation.planning_state import PlanningState


def test_planner_returns_planning_state():
    llm = MagicMock()
    typed = MagicMock()
    typed.goal = "stabilize food"
    typed.goal_type = "survival"
    typed.subgoals = [
        MagicMock(
            description="move toward fruit",
            kind="move",
            target="fruit",
            preconditions=["fruit visible"],
            completion_signal="adjacent to fruit",
            failure_signal="fruit disappears",
            priority=1,
        )
    ]
    typed.horizon = "short"
    typed.success_signals = ["eat fruit"]
    typed.abort_conditions = ["energy <= 10"]
    typed.confidence = 0.8
    typed.rationale_summary = "Hunger is rising and fruit is visible"
    llm.generate_structured.return_value = typed

    planner = Planner(llm=llm)
    state = planner.plan(
        agent_name="Ada",
        tick=5,
        observation_text="fruit east",
        planner_context=["fruit helps"],
    )

    assert isinstance(state, PlanningState)
    assert state.goal == "stabilize food"


def test_planner_returns_none_on_invalid_llm():
    llm = MagicMock()
    llm.generate_structured.return_value = None

    planner = Planner(llm=llm)

    assert planner.plan(
        agent_name="Ada",
        tick=5,
        observation_text="fruit east",
        planner_context=[],
    ) is None
