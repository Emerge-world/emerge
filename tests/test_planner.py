from unittest.mock import MagicMock

from simulation import prompt_loader
from simulation.config import PLANNER_RESPONSE_MAX_TOKENS
from simulation.planner import Planner
from simulation.planning_state import PlanningState


def test_planner_prompt_includes_reflection_questions():
    prompt = prompt_loader.render(
        "agent/planner",
        tick=5,
        observation_text="fruit east",
        planner_context="- fruit helps",
        current_plan="stabilize food",
    )

    assert "What is my long-term goal?" in prompt
    assert "Am I getting closer to that goal?" in prompt
    assert "Could I do this more efficiently?" in prompt
    assert "Do I need to change my goal?" in prompt


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
    assert llm.generate_structured.call_args[1]["max_tokens"] == PLANNER_RESPONSE_MAX_TOKENS


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
