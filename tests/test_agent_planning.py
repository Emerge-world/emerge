from unittest.mock import MagicMock

from simulation.agent import Agent
from simulation.planning_state import PlanningState, PlanningSubgoal
from simulation.schemas import AgentDecisionResponse, AgentPlanResponse, PlanSubgoalResponse


def test_agent_keeps_existing_plan_when_progressing(monkeypatch):
    llm = MagicMock()
    llm.last_call = {}
    llm.generate_structured.side_effect = [
        AgentPlanResponse(
            goal="stabilize food",
            goal_type="survival",
            subgoals=[
                PlanSubgoalResponse(
                    description="move toward fruit",
                    kind="move",
                    target="fruit",
                    preconditions=["fruit visible"],
                    completion_signal="adjacent to fruit",
                    failure_signal="fruit disappears",
                    priority=1,
                )
            ],
            horizon="short",
            success_signals=["eat fruit"],
            abort_conditions=["energy <= 10"],
            confidence=0.8,
            rationale_summary="fruit visible",
        ),
        AgentDecisionResponse(action="move", direction="east", reason="following plan"),
    ]
    agent = Agent(name="Ada", x=5, y=5, llm=llm)
    agent.planning_state = PlanningState(
        goal="stabilize food",
        goal_type="survival",
        subgoals=[PlanningSubgoal(description="move toward fruit", kind="move")],
        active_subgoal_index=0,
        status="stale",
        created_tick=1,
        last_plan_tick=1,
        last_progress_tick=1,
        confidence=0.8,
        horizon="short",
        success_signals=["eat fruit"],
        abort_conditions=[],
        blockers=[],
        rationale_summary="fruit visible",
    )
    monkeypatch.setattr("simulation.agent.ENABLE_EXPLICIT_PLANNING", True)

    action = agent.decide_action([{"x": 5, "y": 5, "tile": "land", "distance": 0}], tick=2)

    assert "_planning_trace" in action
    assert action["_planning_trace"]["plan_created"]["goal"] == "stabilize food"
