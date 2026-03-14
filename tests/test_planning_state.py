from simulation.planning_state import PlanningState, PlanningSubgoal
from simulation.schemas import AgentPlanResponse


def test_empty_planning_state_requires_replan():
    state = PlanningState.empty()

    assert state.needs_replan(tick=1, plan_refresh_interval=5) is True


def test_planning_state_turns_stale_after_refresh_interval():
    state = PlanningState(
        goal="stabilize food",
        goal_type="survival",
        subgoals=[PlanningSubgoal(description="move east", kind="move")],
        active_subgoal_index=0,
        status="active",
        created_tick=1,
        last_plan_tick=1,
        last_progress_tick=1,
        confidence=0.8,
        horizon="short",
        success_signals=["eat fruit"],
        abort_conditions=["life <= 20"],
        blockers=[],
        rationale_summary="food first",
    )

    assert state.needs_replan(tick=7, plan_refresh_interval=5) is True


def test_agent_plan_response_parses_structured_subgoals():
    typed = AgentPlanResponse.model_validate(
        {
            "goal": "stabilize food",
            "goal_type": "survival",
            "subgoals": [
                {
                    "description": "move toward fruit",
                    "kind": "move",
                    "target": "fruit",
                    "preconditions": ["fruit visible"],
                    "completion_signal": "adjacent to fruit",
                    "failure_signal": "fruit no longer visible",
                    "priority": 1,
                }
            ],
            "horizon": "short",
            "success_signals": ["hunger drops below 40"],
            "abort_conditions": ["energy <= 10"],
            "confidence": 0.75,
            "rationale_summary": "Food is visible and hunger is rising",
        }
    )

    assert typed.subgoals[0].kind == "move"
