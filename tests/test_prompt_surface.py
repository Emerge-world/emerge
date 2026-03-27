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


def _decision_kwargs() -> dict:
    return {
        "tick": 7,
        "time_info": "Daylight.",
        "current_tile_info": "[Tile: land]",
        "life": 90,
        "max_life": 100,
        "hunger": 20,
        "max_hunger": 100,
        "hunger_threshold": 80,
        "energy": 70,
        "max_energy": 100,
        "status_effects": "",
        "inventory_info": "INVENTORY: fruit x1",
        "ascii_grid": ". . .",
        "pickup_ready_resources": "- fruit HERE (qty: 1)",
        "nearby_resource_hints": "- mushroom 1 tile EAST (qty: 1)",
        "social_context": {
            "nearby_agents": "NEARBY AGENTS:\n- Bruno 1 tile EAST",
            "incoming_messages": "INCOMING MESSAGES:\n- Bruno: fruit east",
            "relationships": "RELATIONSHIPS:\n- Bruno trust=0.60",
        },
        "planning_context": {
            "current_goal": "stabilize food",
            "active_subgoal": "move toward fruit",
            "plan_status": "status=active, confidence=0.80, horizon=short",
        },
        "family_info": "No known family ties.",
        "memory_text": (
            "KNOWLEDGE (things I've learned):\n"
            "- [KNOW] Fruit reduces hunger.\n\n"
            "RECENT EVENTS:\n"
            "- [RECENT] I moved east."
        ),
        "reproduction_hint": (
            'To reproduce: {"action": "reproduce", "target": "<name>", '
            '"reason": "..."}'
        ),
    }


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


def test_executor_decision_full_matches_golden():
    prompt = _builder().build_executor_decision(**_decision_kwargs())
    _assert_matches_golden("executor_decision_full.txt", prompt)


def test_executor_decision_planning_off_matches_golden():
    prompt = _builder(explicit_planning=False).build_executor_decision(
        **_decision_kwargs()
    )
    _assert_matches_golden("executor_decision_planning_off.txt", prompt)


def test_executor_decision_social_off_matches_golden():
    prompt = _builder(social=False, teach=False).build_executor_decision(
        **_decision_kwargs()
    )
    _assert_matches_golden("executor_decision_social_off.txt", prompt)


def test_executor_decision_reproduction_off_matches_golden():
    prompt = _builder(reproduction=False).build_executor_decision(
        **_decision_kwargs()
    )
    _assert_matches_golden("executor_decision_reproduction_off.txt", prompt)
