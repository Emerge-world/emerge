"""
Unit tests for Phase 4: Reproduction & Inheritance mechanics.
"""

from unittest.mock import MagicMock

from simulation.agent import Agent
from simulation.config import (
    REPRODUCE_MIN_LIFE, REPRODUCE_MAX_HUNGER, REPRODUCE_MIN_ENERGY,
    REPRODUCE_MIN_TICKS_ALIVE, REPRODUCE_COOLDOWN,
    REPRODUCE_LIFE_COST, REPRODUCE_HUNGER_COST, REPRODUCE_ENERGY_COST,
    CHILD_START_LIFE, CHILD_START_HUNGER, CHILD_START_ENERGY,
    BONDING_TRUST_THRESHOLD, PERSONALITY_MUTATION_STD,
)
from simulation.lineage import LineageTracker, LineageRecord
from simulation.memory import Memory
from simulation.oracle import Oracle
from simulation.personality import Personality


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ready_agent(name: str, x: int, y: int, tick: int = 200) -> Agent:
    """Return an agent that meets all reproduction requirements."""
    agent = Agent(name=name, x=x, y=y)
    agent.life = REPRODUCE_MIN_LIFE
    agent.hunger = REPRODUCE_MAX_HUNGER
    agent.energy = REPRODUCE_MIN_ENERGY
    agent.born_tick = 0
    agent.last_reproduce_tick = -(REPRODUCE_COOLDOWN + 1)  # definitely off cooldown
    return agent


def make_world_mock(tile: str = "land") -> MagicMock:
    world = MagicMock()
    world.get_tile.return_value = tile
    return world


def make_oracle(agent_a: Agent, agent_b: Agent, tile: str = "land") -> Oracle:
    oracle = Oracle(world=make_world_mock(tile), llm=None)
    oracle.current_tick_agents = [agent_a, agent_b]
    return oracle


# ---------------------------------------------------------------------------
# Oracle: happy path
# ---------------------------------------------------------------------------

def test_reproduce_success():
    ada = ready_agent("Ada", x=5, y=5)
    bruno = ready_agent("Bruno", x=5, y=6)  # adjacent
    oracle = make_oracle(ada, bruno)
    result = oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert result["success"] is True


def test_reproduce_child_spawn_in_result():
    ada = ready_agent("Ada", x=5, y=5)
    bruno = ready_agent("Bruno", x=5, y=6)
    oracle = make_oracle(ada, bruno)
    result = oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert "child_spawn" in result
    assert result["child_spawn"]["parent_a"] == "Ada"
    assert result["child_spawn"]["parent_b"] == "Bruno"
    assert result["child_spawn"]["pos"] is not None


def test_reproduce_costs_applied_to_both_parents():
    ada = ready_agent("Ada", x=5, y=5)
    bruno = ready_agent("Bruno", x=5, y=6)
    life_before = ada.life
    hunger_before = ada.hunger
    energy_before = ada.energy
    oracle = make_oracle(ada, bruno)
    oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert ada.life == life_before - REPRODUCE_LIFE_COST
    assert ada.hunger == hunger_before + REPRODUCE_HUNGER_COST
    assert ada.energy == energy_before - REPRODUCE_ENERGY_COST
    assert bruno.life == life_before - REPRODUCE_LIFE_COST
    assert bruno.energy == energy_before - REPRODUCE_ENERGY_COST


def test_reproduce_cooldown_updated():
    ada = ready_agent("Ada", x=5, y=5)
    bruno = ready_agent("Bruno", x=5, y=6)
    oracle = make_oracle(ada, bruno)
    oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert ada.last_reproduce_tick == 200
    assert bruno.last_reproduce_tick == 200


def test_reproduce_bonds_parents():
    ada = ready_agent("Ada", x=5, y=5)
    bruno = ready_agent("Bruno", x=5, y=6)
    oracle = make_oracle(ada, bruno)
    oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert "Bruno" in ada.relationships
    assert "Ada" in bruno.relationships


def test_reproduce_adds_memories():
    ada = ready_agent("Ada", x=5, y=5)
    bruno = ready_agent("Bruno", x=5, y=6)
    oracle = make_oracle(ada, bruno)
    oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    ada_memories = " ".join(ada.memory)
    bruno_memories = " ".join(bruno.memory)
    assert "reproduced" in ada_memories.lower() or "Bruno" in ada_memories
    assert "reproduced" in bruno_memories.lower() or "Ada" in bruno_memories


# ---------------------------------------------------------------------------
# Oracle: failure cases
# ---------------------------------------------------------------------------

def test_reproduce_target_not_found():
    ada = ready_agent("Ada", x=5, y=5)
    oracle = Oracle(world=make_world_mock(), llm=None)
    oracle.current_tick_agents = [ada]
    result = oracle.resolve_action(ada, {"action": "reproduce", "target": "Ghost"}, tick=200)
    assert result["success"] is False


def test_reproduce_target_dead():
    ada = ready_agent("Ada", x=5, y=5)
    bruno = ready_agent("Bruno", x=5, y=6)
    bruno.alive = False
    oracle = Oracle(world=make_world_mock(), llm=None)
    oracle.current_tick_agents = [ada, bruno]
    result = oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert result["success"] is False


def test_reproduce_not_adjacent():
    ada = ready_agent("Ada", x=5, y=5)
    bruno = ready_agent("Bruno", x=5, y=8)  # distance 3 > 1
    oracle = make_oracle(ada, bruno)
    result = oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert result["success"] is False


def test_reproduce_initiator_low_life():
    ada = ready_agent("Ada", x=5, y=5)
    ada.life = REPRODUCE_MIN_LIFE - 1
    bruno = ready_agent("Bruno", x=5, y=6)
    oracle = make_oracle(ada, bruno)
    result = oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert result["success"] is False


def test_reproduce_initiator_too_hungry():
    ada = ready_agent("Ada", x=5, y=5)
    ada.hunger = REPRODUCE_MAX_HUNGER + 1
    bruno = ready_agent("Bruno", x=5, y=6)
    oracle = make_oracle(ada, bruno)
    result = oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert result["success"] is False


def test_reproduce_initiator_low_energy():
    ada = ready_agent("Ada", x=5, y=5)
    ada.energy = REPRODUCE_MIN_ENERGY - 1
    bruno = ready_agent("Bruno", x=5, y=6)
    oracle = make_oracle(ada, bruno)
    result = oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert result["success"] is False


def test_reproduce_too_young():
    ada = ready_agent("Ada", x=5, y=5)
    ada.born_tick = 150  # only 49 ticks old at tick=200
    bruno = ready_agent("Bruno", x=5, y=6)
    oracle = make_oracle(ada, bruno)
    result = oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert result["success"] is False


def test_reproduce_on_cooldown():
    ada = ready_agent("Ada", x=5, y=5)
    ada.last_reproduce_tick = 180  # cooldown expires at 180 + 48 = 228
    bruno = ready_agent("Bruno", x=5, y=6)
    oracle = make_oracle(ada, bruno)
    result = oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert result["success"] is False


def test_reproduce_target_low_life():
    ada = ready_agent("Ada", x=5, y=5)
    bruno = ready_agent("Bruno", x=5, y=6)
    bruno.life = REPRODUCE_MIN_LIFE - 1
    oracle = make_oracle(ada, bruno)
    result = oracle.resolve_action(ada, {"action": "reproduce", "target": "Bruno"}, tick=200)
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Personality.blend()
# ---------------------------------------------------------------------------

def test_personality_blend_average():
    """Child traits should be close to the average of parents."""
    p_a = Personality(courage=0.0, curiosity=0.0, patience=0.0, sociability=0.0)
    p_b = Personality(courage=1.0, curiosity=1.0, patience=1.0, sociability=1.0)
    # Run many times; average should converge near 0.5
    samples = [Personality.blend(p_a, p_b).courage for _ in range(200)]
    avg = sum(samples) / len(samples)
    assert 0.3 < avg < 0.7, f"Expected avg near 0.5, got {avg}"


def test_personality_blend_clamped():
    """Mutation must not push traits outside [0, 1]."""
    p_a = Personality(courage=0.0, curiosity=0.0, patience=0.0, sociability=0.0)
    p_b = Personality(courage=0.0, curiosity=0.0, patience=0.0, sociability=0.0)
    for _ in range(100):
        child = Personality.blend(p_a, p_b)
        assert 0.0 <= child.courage <= 1.0
        assert 0.0 <= child.curiosity <= 1.0
        assert 0.0 <= child.patience <= 1.0
        assert 0.0 <= child.sociability <= 1.0


def test_personality_blend_returns_personality():
    p_a = Personality.random()
    p_b = Personality.random()
    child = Personality.blend(p_a, p_b)
    assert isinstance(child, Personality)


# ---------------------------------------------------------------------------
# Memory.inherit_from()
# ---------------------------------------------------------------------------

def test_memory_inherit_seeds_semantic():
    parent_a = Memory()
    parent_a.add_knowledge("Rivers are dangerous to cross alone.")
    parent_a.add_knowledge("Mushrooms in the forest are edible.")
    parent_b = Memory()
    parent_b.add_knowledge("Caves provide shelter at night.")
    child = Memory()
    child.inherit_from(parent_a, parent_b)
    assert len(child.semantic) == 3


def test_memory_inherit_prefixed():
    parent_a = Memory()
    parent_a.add_knowledge("Stone is hard.")
    parent_b = Memory()
    child = Memory()
    child.inherit_from(parent_a, parent_b)
    assert all(e.startswith("[Inherited]") for e in child.semantic)


def test_memory_inherit_no_episodes():
    parent_a = Memory()
    parent_a.add_episode("I ate a fruit at tick 5.")
    parent_b = Memory()
    child = Memory()
    child.inherit_from(parent_a, parent_b)
    # Episodes should NOT be inherited
    assert len(child.episodic) == 0


def test_memory_inherit_max_per_parent():
    """Caps at INHERIT_SEMANTIC_MAX entries per parent."""
    from simulation.config import INHERIT_SEMANTIC_MAX
    parent_a = Memory()
    for i in range(INHERIT_SEMANTIC_MAX + 5):
        parent_a.add_knowledge(f"Lesson {i}")
    parent_b = Memory()
    child = Memory()
    child.inherit_from(parent_a, parent_b)
    assert len(child.semantic) <= INHERIT_SEMANTIC_MAX


# ---------------------------------------------------------------------------
# LineageTracker
# ---------------------------------------------------------------------------

def test_lineage_record_birth():
    tracker = LineageTracker()
    tracker.record_birth("Ada", [], 0, tick=0)
    assert "Ada" in tracker.records
    assert tracker.records["Ada"].generation == 0
    assert tracker.records["Ada"].parent_names == []


def test_lineage_record_death():
    tracker = LineageTracker()
    tracker.record_birth("Ada", [], 0, tick=0)
    tracker.record_death("Ada", tick=50)
    assert tracker.records["Ada"].died_tick == 50


def test_lineage_record_innovation():
    tracker = LineageTracker()
    tracker.record_birth("Ada", [], 0, tick=0)
    tracker.record_innovation("Ada", "fire_making")
    assert "fire_making" in tracker.records["Ada"].innovations_created


def test_lineage_record_child():
    tracker = LineageTracker()
    tracker.record_birth("Ada", [], 0, tick=0)
    tracker.record_child("Ada", "Kira")
    assert "Kira" in tracker.records["Ada"].children_names


def test_lineage_save_load(tmp_path):
    tracker = LineageTracker()
    tracker.record_birth("Ada", [], 0, tick=0)
    tracker.record_birth("Kira", ["Ada", "Bruno"], 1, tick=150)
    tracker.record_death("Ada", tick=300)
    path = str(tmp_path / "lineage.json")
    tracker.save(path)
    tracker2 = LineageTracker()
    tracker2.load(path)
    assert "Ada" in tracker2.records
    assert tracker2.records["Ada"].died_tick == 300
    assert tracker2.records["Kira"].generation == 1
    assert tracker2.records["Kira"].parent_names == ["Ada", "Bruno"]


def test_lineage_load_missing_file(tmp_path):
    """Loading a nonexistent file should silently succeed."""
    tracker = LineageTracker()
    tracker.load(str(tmp_path / "nonexistent.json"))
    assert len(tracker.records) == 0


# ---------------------------------------------------------------------------
# Agent.get_family_prompt()
# ---------------------------------------------------------------------------

def test_family_prompt_gen0():
    agent = Agent(name="Ada", x=0, y=0)
    prompt = agent.get_family_prompt(current_tick=10)
    assert "generation 0" in prompt


def test_family_prompt_gen1():
    agent = Agent(name="Kira", x=0, y=0)
    agent.generation = 1
    agent.born_tick = 100
    agent.parent_ids = ["Ada", "Bruno"]
    prompt = agent.get_family_prompt(current_tick=200)
    assert "generation 1" in prompt
    assert "Ada" in prompt
    assert "Bruno" in prompt


def test_family_prompt_shows_children():
    parent = Agent(name="Ada", x=0, y=0)
    parent.children_names = ["Kira"]
    child_agent = Agent(name="Kira", x=1, y=0)
    prompt = parent.get_family_prompt(current_tick=200, all_agents=[parent, child_agent])
    assert "Kira" in prompt


def test_family_prompt_cooldown_message():
    agent = Agent(name="Ada", x=0, y=0)
    agent.last_reproduce_tick = 190  # cooldown expires at 190 + 48 = 238
    prompt = agent.get_family_prompt(current_tick=200)
    assert "cooldown" in prompt.lower()
