from pathlib import Path

from simulation.prompt_surface import PromptSurfaceBuilder
from simulation.runtime_policy import AgentRuntimeSettings, MemoryRuntimeSettings


GOLDEN_DIR = Path(__file__).parent / "golden" / "prompts"


def _builder(**caps: bool) -> PromptSurfaceBuilder:
    return PromptSurfaceBuilder(
        agent_settings=AgentRuntimeSettings(
            explicit_planning=caps.get("explicit_planning", True),
            innovation=caps.get("innovation", True),
            item_reflection=caps.get("item_reflection", True),
            social=caps.get("social", True),
            teach=caps.get("teach", True),
            reproduction=caps.get("reproduction", True),
        ),
        memory_settings=MemoryRuntimeSettings(
            semantic_memory=caps.get("semantic_memory", True)
        ),
    )


def _assert_matches_golden(name: str, text: str) -> None:
    assert text == (GOLDEN_DIR / name).read_text()


def test_executor_system_full_matches_golden():
    prompt = _builder().build_executor_system(
        name="Ada",
        actions=[
            "move",
            "eat",
            "rest",
            "pickup",
            "drop_item",
            "innovate",
            "communicate",
            "give_item",
            "teach",
            "reflect_item_uses",
        ],
        personality_description="You are curious but patient.",
        action_descriptions={},
    )
    _assert_matches_golden("executor_system_full.txt", prompt)


def test_executor_system_innovation_off_matches_golden():
    prompt = _builder(innovation=False).build_executor_system(
        name="Ada",
        actions=[
            "move",
            "eat",
            "rest",
            "pickup",
            "drop_item",
            "communicate",
            "give_item",
            "teach",
            "reflect_item_uses",
        ],
        personality_description="You are curious but patient.",
        action_descriptions={"cut_branches": "cut branches with a sharp tool"},
    )
    _assert_matches_golden("executor_system_innovation_off.txt", prompt)


def test_executor_system_social_off_matches_golden():
    prompt = _builder(social=False, teach=False).build_executor_system(
        name="Ada",
        actions=[
            "move",
            "eat",
            "rest",
            "pickup",
            "drop_item",
            "innovate",
            "reflect_item_uses",
        ],
        personality_description="You are curious but patient.",
        action_descriptions={},
    )
    _assert_matches_golden("executor_system_social_off.txt", prompt)
