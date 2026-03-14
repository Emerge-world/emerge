from unittest.mock import MagicMock

from simulation.agent import Agent
from simulation.config import DECISION_RESPONSE_MAX_TOKENS
from simulation.oracle import Oracle
from simulation.planning_state import PlanningState, PlanningSubgoal
from simulation.schemas import AgentDecisionResponse, AgentPlanResponse, PlanSubgoalResponse
from simulation.world import World


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


def test_successful_replan_includes_planner_llm_trace(monkeypatch):
    llm = MagicMock()
    llm.last_call = {}

    plan_response = AgentPlanResponse(
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
    )
    decision_response = AgentDecisionResponse(
        action="move",
        direction="east",
        reason="following plan",
    )

    def fake_generate_structured(prompt, schema, system_prompt="", temperature=None, max_tokens=None):
        if schema is AgentPlanResponse:
            llm.last_call = {
                "system_prompt": system_prompt,
                "user_prompt": prompt,
                "raw_response": '{"goal":"stabilize food"}',
            }
            return plan_response
        llm.last_call = {
            "system_prompt": system_prompt,
            "user_prompt": prompt,
            "raw_response": '{"action":"move","direction":"east","reason":"following plan"}',
        }
        return decision_response

    llm.generate_structured.side_effect = fake_generate_structured
    agent = Agent(name="Ada", x=5, y=5, llm=llm)
    monkeypatch.setattr("simulation.agent.ENABLE_EXPLICIT_PLANNING", True)

    action = agent.decide_action([{"x": 5, "y": 5, "tile": "land", "distance": 0}], tick=2)

    planner_trace = action["_planning_trace"]["planner_llm"]
    assert planner_trace["system_prompt"]
    assert "Build or refresh your plan" in planner_trace["user_prompt"]
    assert planner_trace["raw_response"] == '{"goal":"stabilize food"}'
    assert planner_trace["parsed_plan"]["goal"] == "stabilize food"


def test_decide_action_omits_none_fields_before_oracle_eat_resolution():
    llm = MagicMock()
    llm.last_call = {}
    llm.generate_structured.return_value = AgentDecisionResponse(action="eat", reason="hungry")

    world = World(width=5, height=5, seed=42)
    agent = Agent(name="Ada", x=2, y=2, llm=llm)
    for pos in [(2, 2), (3, 2), (1, 2), (2, 3), (2, 1)]:
        world.resources.pop(pos, None)
    oracle = Oracle(world=world, llm=None)

    action = agent.decide_action([{"x": 2, "y": 2, "tile": "land", "distance": 0}], tick=1)

    assert "item" not in action
    assert llm.generate_structured.call_args[1]["max_tokens"] == DECISION_RESPONSE_MAX_TOKENS
    result = oracle.resolve_action(agent, action, tick=1)
    assert result["success"] is False
