from unittest.mock import MagicMock

from simulation.config import PLANNER_RESPONSE_MAX_TOKENS
from simulation.planner import Planner
from simulation.prompt_surface import PromptSurfaceBuilder
from simulation.planning_state import PlanningState
from simulation.runtime_policy import AgentRuntimeSettings, MemoryRuntimeSettings


def _builder(**caps):
    return PromptSurfaceBuilder(
        agent_settings=AgentRuntimeSettings(
            explicit_planning=caps.get("explicit_planning", True),
            innovation=caps.get("innovation", True),
            item_reflection=caps.get("item_reflection", True),
            social=caps.get("social", True),
            teach=caps.get("teach", True),
            reproduction=caps.get("reproduction", True),
        ),
        memory_settings=MemoryRuntimeSettings(semantic_memory=True),
    )


def test_planner_prompt_includes_updated_reflection_questions():
    builder = _builder()
    observation = builder.build_planner_observation_text(
        life=90,
        hunger=20,
        energy=70,
        inventory_info="INVENTORY: fruit x1",
        current_tile_resources="fruit",
        nearby_resources="mushroom",
        nearby_agent_names=["Bruno"],
        custom_actions=["cut_branches"],
        time_description="Daylight.",
    )
    prompt = builder.build_planner_prompt(
        tick=5,
        observation_text=observation,
        planner_context=["fruit helps"],
        current_plan="stabilize food",
    )

    assert "What most needs attention over the next few ticks?" in prompt
    assert "Am I getting closer to a better position, capability, or relationship?" in prompt
    assert "Am I repeating actions without progress?" in prompt
    assert "Is there a blocked opportunity that suggests innovation or a different approach?" in prompt
    assert "If survival is stable, should I prepare for cooperation, teaching, or reproduction?" in prompt
    assert "Do I need to change my goal?" in prompt


def test_planner_system_requires_movement_before_pickup_for_nearby_items():
    prompt = _builder().build_planner_system(agent_name="Ada")

    assert "move" in prompt.lower()
    assert "before" in prompt.lower()
    assert "pickup" in prompt.lower()


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

    planner = Planner(llm=llm, prompt_surface=_builder())
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

    planner = Planner(llm=llm, prompt_surface=_builder())

    assert planner.plan(
        agent_name="Ada",
        tick=5,
        observation_text="fruit east",
        planner_context=[],
    ) is None


def test_planner_prompt_omits_innovation_question_when_innovation_disabled():
    builder = _builder(innovation=False)
    observation = builder.build_planner_observation_text(
        life=90,
        hunger=20,
        energy=70,
        inventory_info="INVENTORY: fruit x1",
        current_tile_resources="fruit",
        nearby_resources="mushroom",
        nearby_agent_names=["Bruno"],
        custom_actions=["cut_branches"],
        time_description="Daylight.",
    )
    prompt = builder.build_planner_prompt(
        tick=5,
        observation_text=observation,
        planner_context=["fruit helps"],
        current_plan="stabilize food",
    )

    assert "suggests innovation" not in prompt


def test_planner_prompt_omits_social_progress_question_when_social_disabled():
    builder = _builder(social=False, teach=False)
    observation = builder.build_planner_observation_text(
        life=90,
        hunger=20,
        energy=70,
        inventory_info="INVENTORY: fruit x1",
        current_tile_resources="fruit",
        nearby_resources="mushroom",
        nearby_agent_names=["Bruno"],
        custom_actions=["cut_branches"],
        time_description="Daylight.",
    )
    prompt = builder.build_planner_prompt(
        tick=5,
        observation_text=observation,
        planner_context=["fruit helps"],
        current_plan="stabilize food",
    )

    assert "relationship" not in prompt
    assert "cooperation" not in prompt


def test_planner_system_omits_reproduction_guidance_when_reproduction_disabled():
    prompt = _builder(reproduction=False).build_planner_system(agent_name="Ada")

    assert "future reproduction" not in prompt
