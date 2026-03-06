# Phase 3a: Personality + Social Perception — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give each agent a randomized personality injected into their LLM system prompt, and let agents see nearby agents in their decision prompt with fuzzy stats.

**Architecture:** New `simulation/personality.py` dataclass; `Agent` gains a `personality` field and `nearby_agents_prompt()` method; `World` gains `get_agents_in_radius()`; engine passes nearby agents to `decide_action()` each tick; two prompt templates updated.

**Tech Stack:** Python dataclasses, `string.Template` prompt rendering, `pytest` for tests. Use `uv run` for all commands.

**Design doc:** `docs/plans/2026-03-06-phase3-social-design.md` — Phase 3a section.

---

## Pre-flight

Run existing tests to confirm a clean baseline:
```bash
uv run pytest -m "not slow" -q
```
Expected: all pass. If anything fails, stop and fix before proceeding.

---

## Task 1: Personality Dataclass

**Files:**
- Create: `simulation/personality.py`
- Create: `tests/test_personality.py`

### Step 1: Write the failing tests

Create `tests/test_personality.py`:

```python
"""Tests for the Personality dataclass."""
import pytest
from simulation.personality import Personality


class TestPersonalityCreation:
    def test_direct_construction(self):
        p = Personality(courage=0.8, curiosity=0.3, patience=0.6, sociability=0.1)
        assert p.courage == 0.8
        assert p.curiosity == 0.3
        assert p.patience == 0.6
        assert p.sociability == 0.1

    def test_random_creates_personality(self):
        p = Personality.random()
        assert isinstance(p, Personality)

    def test_random_traits_in_range(self):
        for _ in range(20):
            p = Personality.random()
            assert 0.0 <= p.courage <= 1.0
            assert 0.0 <= p.curiosity <= 1.0
            assert 0.0 <= p.patience <= 1.0
            assert 0.0 <= p.sociability <= 1.0

    def test_random_produces_variety(self):
        """Different calls should produce different values."""
        values = {Personality.random().courage for _ in range(20)}
        assert len(values) > 1


class TestPersonalityToPrompt:
    def test_to_prompt_is_non_empty(self):
        p = Personality(courage=0.8, curiosity=0.3, patience=0.6, sociability=0.1)
        assert len(p.to_prompt()) > 0

    def test_to_prompt_contains_all_trait_names(self):
        p = Personality(courage=0.8, curiosity=0.3, patience=0.6, sociability=0.1)
        text = p.to_prompt()
        assert "courage" in text.lower()
        assert "curiosity" in text.lower()
        assert "patience" in text.lower()
        assert "sociability" in text.lower()

    def test_to_prompt_contains_numeric_values(self):
        p = Personality(courage=0.80, curiosity=0.30, patience=0.60, sociability=0.10)
        text = p.to_prompt()
        assert "0.80" in text
        assert "0.30" in text
        assert "0.60" in text
        assert "0.10" in text

    def test_to_prompt_high_label(self):
        p = Personality(courage=0.9, curiosity=0.5, patience=0.5, sociability=0.5)
        assert "high" in p.to_prompt().lower()

    def test_to_prompt_very_low_label(self):
        p = Personality(courage=0.1, curiosity=0.5, patience=0.5, sociability=0.5)
        assert "very low" in p.to_prompt().lower()
```

### Step 2: Run the tests to verify they fail

```bash
uv run pytest tests/test_personality.py -v
```
Expected: `ModuleNotFoundError: No module named 'simulation.personality'`

### Step 3: Implement `simulation/personality.py`

```python
"""
Personality traits for agents.
Injected into the LLM system prompt to shape emergent behavior.
"""

import random
from dataclasses import dataclass


@dataclass
class Personality:
    courage: float     # 0.0-1.0: boldness, willingness to take risks
    curiosity: float   # 0.0-1.0: tendency to explore and innovate
    patience: float    # 0.0-1.0: willingness to wait vs. act immediately
    sociability: float # 0.0-1.0: tendency to seek out and interact with others

    @classmethod
    def random(cls) -> "Personality":
        """Create a personality with randomized traits."""
        return cls(
            courage=round(random.random(), 2),
            curiosity=round(random.random(), 2),
            patience=round(random.random(), 2),
            sociability=round(random.random(), 2),
        )

    def to_prompt(self) -> str:
        """Return a description for injection into the LLM system prompt."""
        def label(v: float) -> str:
            if v >= 0.75:
                return "high"
            if v >= 0.50:
                return "moderate"
            if v >= 0.25:
                return "low"
            return "very low"

        return (
            f"Personality traits — "
            f"courage: {label(self.courage)} ({self.courage:.2f}), "
            f"curiosity: {label(self.curiosity)} ({self.curiosity:.2f}), "
            f"patience: {label(self.patience)} ({self.patience:.2f}), "
            f"sociability: {label(self.sociability)} ({self.sociability:.2f})."
        )
```

### Step 4: Run tests to verify they pass

```bash
uv run pytest tests/test_personality.py -v
```
Expected: all 9 tests PASS.

### Step 5: Commit

```bash
git add simulation/personality.py tests/test_personality.py
git commit -m "feat(phase3a): add Personality dataclass with prompt injection support"
```

---

## Task 2: Agent Personality Field + System Prompt Injection

**Files:**
- Modify: `simulation/agent.py` (add import, field, and pass to system prompt)
- Modify: `prompts/agent/system.txt` (add `$personality_description` variable)
- Modify: `tests/test_agent_prompts.py` (add personality tests)

### Step 1: Write failing tests

Add to `tests/test_agent_prompts.py`:

```python
# Add at the top with other imports:
from simulation.personality import Personality


class TestPersonalityInAgent:
    def setup_method(self):
        Agent._id_counter = 0

    def test_agent_has_personality_by_default(self):
        agent = Agent(name="Ada", x=5, y=5)
        assert hasattr(agent, "personality")
        assert isinstance(agent.personality, Personality)

    def test_agent_personality_traits_in_range(self):
        agent = Agent(name="Ada", x=5, y=5)
        assert 0.0 <= agent.personality.courage <= 1.0
        assert 0.0 <= agent.personality.sociability <= 1.0

    def test_system_prompt_contains_personality(self):
        agent = Agent(name="Ada", x=5, y=5)
        agent.personality = Personality(courage=0.9, curiosity=0.1, patience=0.5, sociability=0.7)
        prompt = agent._build_system_prompt()
        assert "courage" in prompt.lower()
        assert "0.90" in prompt

    def test_system_prompt_personality_is_dynamic(self):
        """Different personalities produce different prompts."""
        agent = Agent(name="Ada", x=5, y=5)
        agent.personality = Personality(courage=0.1, curiosity=0.1, patience=0.1, sociability=0.1)
        prompt_low = agent._build_system_prompt()
        agent.personality = Personality(courage=0.9, curiosity=0.9, patience=0.9, sociability=0.9)
        prompt_high = agent._build_system_prompt()
        assert prompt_low != prompt_high
```

### Step 2: Run the tests to verify they fail

```bash
uv run pytest tests/test_agent_prompts.py::TestPersonalityInAgent -v
```
Expected: FAIL (Agent has no `personality` attribute yet)

### Step 3: Modify `prompts/agent/system.txt`

Add `$personality_description` after line 2. The full new content:

```
You are $name, a human trying to survive in a 2D world.
You must choose actions wisely to stay alive.
$personality_description

Available actions: $actions

GRID LEGEND:
  @=you  .=land  S=sand  ~=river  W=water
  F=fruit-tree  t=empty-tree  f=forest  M=mountain  C=cave  #=bounds

Action format — respond with a JSON object:
- move: {"action": "move", "direction": "north|northeast|east|southeast|south|southwest|west|northwest", "reason": "..."}
- eat: {"action": "eat", "reason": "..."} (eat food at current or adjacent tile)
- rest: {"action": "rest", "reason": "..."} (recover energy, skip turn)
- pickup: {"action": "pickup", "reason": "..."} (collect 1 item from current tile into inventory)
- innovate: {"action": "innovate", "new_action_name": "...", "description": "...", "reason": "...", "requires": {"tile": "cave|forest|mountain|river|...", "min_energy": <n>, "items": {"stone": 2}}, "produces": {"knife": 1}}
  (requires and produces are optional. Use requires.tile when the action only makes sense in a specific terrain type. Use produces when your action creates a physical item from materials.)
- For approved innovations: {"action": "<action_name>", "reason": "...", ...extra_params}

DIRECTIONS: north=up south=down west=left east=right (+ diagonals: northeast, northwest, southeast, southwest)

Always respond ONLY with a valid JSON object. Be strategic about survival.
```

### Step 4: Modify `simulation/agent.py`

**a) Add import** at top (after existing imports):
```python
from simulation.personality import Personality
```

**b) In `__init__`, after `self.inventory = ...` line (~line 65), add:**
```python
# Personality traits (injected into system prompt)
self.personality = Personality.random()
```

**c) Update `_build_system_prompt()` to pass `personality_description`:**

Replace the existing method:
```python
def _build_system_prompt(self) -> str:
    return prompt_loader.render(
        "agent/system",
        name=self.name,
        actions=", ".join(self.actions),
        personality_description=self.personality.to_prompt(),
    )
```

### Step 5: Run tests to verify they pass

```bash
uv run pytest tests/test_agent_prompts.py -v
```
Expected: all existing tests + 4 new ones PASS.

Also run the full suite to confirm nothing broke:
```bash
uv run pytest -m "not slow" -q
```
Expected: all pass.

### Step 6: Commit

```bash
git add simulation/agent.py prompts/agent/system.txt tests/test_agent_prompts.py
git commit -m "feat(phase3a): inject agent personality into LLM system prompt"
```

---

## Task 3: World Social Perception (`get_agents_in_radius`)

**Files:**
- Modify: `simulation/world.py` (add method)
- Create: `tests/test_perception.py` (new test file)

### Step 1: Write failing tests

Create `tests/test_perception.py`:

```python
"""Tests for social perception: agents seeing other agents."""
import pytest
from simulation.agent import Agent
from simulation.world import World
from simulation.config import AGENT_VISION_RADIUS


class TestGetAgentsInRadius:
    def setup_method(self):
        Agent._id_counter = 0
        self.world = World(width=15, height=15, seed=42)

    def test_finds_agent_within_radius(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=5)  # Manhattan distance 2
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=3)
        assert len(result) == 1
        assert result[0][0].name == "Bruno"
        assert result[0][1] == 2

    def test_excludes_self(self):
        agent = Agent(name="Ada", x=5, y=5)
        result = self.world.get_agents_in_radius(agent, [agent], radius=3)
        assert result == []

    def test_excludes_dead_agents(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.alive = False
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=3)
        assert result == []

    def test_excludes_agent_beyond_radius(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=9, y=5)  # distance 4, beyond radius 3
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=3)
        assert result == []

    def test_includes_agent_exactly_at_radius(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=8, y=5)  # distance exactly 3
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=3)
        assert len(result) == 1

    def test_returns_sorted_by_distance(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=5)  # distance 2
        agent_c = Agent(name="Clara", x=6, y=5)  # distance 1
        result = self.world.get_agents_in_radius(
            agent_a, [agent_a, agent_b, agent_c], radius=3
        )
        assert len(result) == 2
        assert result[0][0].name == "Clara"   # closer first
        assert result[0][1] == 1
        assert result[1][0].name == "Bruno"
        assert result[1][1] == 2

    def test_empty_agents_list(self):
        agent = Agent(name="Ada", x=5, y=5)
        result = self.world.get_agents_in_radius(agent, [], radius=3)
        assert result == []

    def test_night_vision_radius(self):
        """Radius 1 (night) should not see agents at distance 2."""
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=5)  # distance 2
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=1)
        assert result == []

    def test_uses_manhattan_distance(self):
        """Distance is |dx| + |dy|, not Euclidean."""
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=7)  # Manhattan=4, Euclidean≈2.8
        result = self.world.get_agents_in_radius(agent_a, [agent_a, agent_b], radius=3)
        assert result == []  # Manhattan distance 4 > radius 3
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_perception.py -v
```
Expected: `AttributeError: 'World' object has no attribute 'get_agents_in_radius'`

### Step 3: Add `get_agents_in_radius` to `simulation/world.py`

Add this method at the end of the `World` class (after `get_summary()`):

```python
def get_agents_in_radius(
    self,
    agent: object,
    agents_list: list,
    radius: int,
) -> list[tuple]:
    """
    Return alive agents within Manhattan distance `radius` of `agent`,
    excluding `agent` itself. Results sorted by distance (closest first).

    Returns list of (agent, distance) tuples.
    """
    result = []
    for other in agents_list:
        if other is agent:
            continue
        if not other.alive:
            continue
        distance = abs(other.x - agent.x) + abs(other.y - agent.y)
        if distance <= radius:
            result.append((other, distance))
    result.sort(key=lambda t: t[1])
    return result
```

### Step 4: Run tests to verify they pass

```bash
uv run pytest tests/test_perception.py -v
```
Expected: all 9 tests PASS.

```bash
uv run pytest -m "not slow" -q
```
Expected: all pass.

### Step 5: Commit

```bash
git add simulation/world.py tests/test_perception.py
git commit -m "feat(phase3a): add World.get_agents_in_radius() for social perception"
```

---

## Task 4: Agent `nearby_agents_prompt()` Method

**Files:**
- Modify: `simulation/agent.py` (add method)
- Modify: `tests/test_perception.py` (add prompt tests)

### Step 1: Add failing tests to `tests/test_perception.py`

Append this class to `tests/test_perception.py`:

```python
class TestNearbyAgentsPrompt:
    def setup_method(self):
        Agent._id_counter = 0

    def test_empty_list_returns_empty_string(self):
        agent = Agent(name="Ada", x=5, y=5)
        assert agent.nearby_agents_prompt([]) == ""

    def test_contains_nearby_agents_header(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=5)
        result = agent_a.nearby_agents_prompt([(agent_b, 2)])
        assert "NEARBY AGENTS:" in result

    def test_shows_agent_name_and_position(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=7, y=5)
        result = agent_a.nearby_agents_prompt([(agent_b, 2)])
        assert "Bruno" in result
        assert "(7,5)" in result
        assert "2 tiles" in result

    def test_singular_tile_at_distance_1(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "1 tile away" in result

    def test_shows_hungry_status(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.hunger = 75  # above 50 threshold
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "hungry" in result.lower()

    def test_not_hungry_when_below_threshold(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.hunger = 30  # below 50 threshold
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "hungry" not in result.lower()

    def test_shows_tired_status(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.energy = 20  # below 30 threshold
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "tired" in result.lower()

    def test_shows_hurt_status(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.life = 40  # below 50 threshold
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "hurt" in result.lower()

    def test_shows_carrying_items_status(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_b.inventory.add("fruit", 2)
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "carrying" in result.lower()

    def test_healthy_agent_shows_healthy(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        # Default stats: hunger=0, energy=100, life=100, empty inventory
        result = agent_a.nearby_agents_prompt([(agent_b, 1)])
        assert "healthy" in result.lower()

    def test_multiple_agents_in_prompt(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        agent_c = Agent(name="Clara", x=7, y=5)
        result = agent_a.nearby_agents_prompt([(agent_b, 1), (agent_c, 2)])
        assert "Bruno" in result
        assert "Clara" in result
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_perception.py::TestNearbyAgentsPrompt -v
```
Expected: `AttributeError: 'Agent' object has no attribute 'nearby_agents_prompt'`

### Step 3: Add `nearby_agents_prompt()` to `simulation/agent.py`

Add this method in the `Agent` class, after `get_recent_memory()` and before `decide_action()`:

```python
def nearby_agents_prompt(self, visible_agents: list[tuple]) -> str:
    """
    Format nearby agents for the decision prompt.
    Returns empty string if no agents are visible (omits the section entirely).
    Uses fuzzy stats to avoid revealing exact numbers.
    """
    if not visible_agents:
        return ""

    lines = ["NEARBY AGENTS:"]
    for other, distance in visible_agents:
        status_parts = []
        if other.hunger > 50:
            status_parts.append("looks hungry")
        if other.energy < 30:
            status_parts.append("looks tired")
        if other.life < 50:
            status_parts.append("looks hurt")
        if other.inventory.items:
            status_parts.append("carrying items")
        status = ". ".join(status_parts).capitalize() if status_parts else "Looks healthy"
        tile_word = "tile" if distance == 1 else "tiles"
        lines.append(
            f"- {other.name} @ ({other.x},{other.y}), {distance} {tile_word} away. {status}."
        )
    return "\n".join(lines)
```

### Step 4: Run tests to verify they pass

```bash
uv run pytest tests/test_perception.py -v
```
Expected: all tests PASS (both `TestGetAgentsInRadius` and `TestNearbyAgentsPrompt`).

```bash
uv run pytest -m "not slow" -q
```
Expected: all pass.

### Step 5: Commit

```bash
git add simulation/agent.py tests/test_perception.py
git commit -m "feat(phase3a): add Agent.nearby_agents_prompt() with fuzzy stat display"
```

---

## Task 5: Wire Social Perception into Engine + Decision Prompt

**Files:**
- Modify: `prompts/agent/decision.txt` (add `$nearby_agents` section)
- Modify: `simulation/agent.py` (update `decide_action` and `_build_decision_prompt` signatures)
- Modify: `simulation/engine.py` (gather nearby agents per tick, pass to decide_action)
- Modify: `tests/test_agent_prompts.py` (add prompt wiring tests)

### Step 1: Write failing tests

Add to `tests/test_agent_prompts.py`:

```python
class TestNearbyAgentsInDecisionPrompt:
    def setup_method(self):
        Agent._id_counter = 0

    def _make_nearby(self, center_tile="land"):
        return [{"x": 5, "y": 5, "tile": center_tile, "distance": 0}]

    def test_no_nearby_agents_omits_section(self):
        agent = Agent(name="Ada", x=5, y=5)
        nearby = self._make_nearby()
        prompt = agent._build_decision_prompt(nearby, tick=1, nearby_agents=[])
        assert "NEARBY AGENTS" not in prompt

    def test_nearby_agents_appears_in_prompt(self):
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        nearby = self._make_nearby()
        prompt = agent_a._build_decision_prompt(
            nearby, tick=1, nearby_agents=[(agent_b, 1)]
        )
        assert "NEARBY AGENTS:" in prompt
        assert "Bruno" in prompt

    def test_decide_action_accepts_nearby_agents(self):
        """decide_action should not crash when nearby_agents is provided."""
        agent_a = Agent(name="Ada", x=5, y=5)
        agent_b = Agent(name="Bruno", x=6, y=5)
        nearby = self._make_nearby()
        # No LLM — uses fallback; should not raise
        result = agent_a.decide_action(nearby, tick=1, nearby_agents=[(agent_b, 1)])
        assert "action" in result
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_agent_prompts.py::TestNearbyAgentsInDecisionPrompt -v
```
Expected: FAIL (signature mismatch or template variable missing)

### Step 3: Update `prompts/agent/decision.txt`

Add `$nearby_agents` after the resources section. Full new content:

```
$time_info
$current_tile_info
TICK $tick - What do you do next?

YOUR STATS: Life=$life/$max_life, Hunger=$hunger/$max_hunger (danger at ${hunger_threshold}+), Energy=$energy/$max_energy
$status_effects
$inventory_info
YOUR VISION (7x7 grid, you are @):
$ascii_grid

NEARBY RESOURCES:
$resource_hints
$nearby_agents

YOUR MEMORY:
$memory_text

Respond with a JSON object.
```

### Step 4: Update `simulation/agent.py` — `decide_action` and `_build_decision_prompt`

**a) Update `decide_action()` signature** (add `nearby_agents` parameter):

```python
def decide_action(self, nearby_tiles: list[dict], tick: int,
                  time_description: str = "",
                  nearby_agents: list | None = None) -> dict:
    """
    Ask the LLM to decide what action to take.
    Returns a dict with the action and its parameters.
    """
    if not self.alive:
        return {"action": "none", "reason": "I am dead"}

    if not self.llm:
        return self._fallback_decision(nearby_tiles)

    system_prompt = self._build_system_prompt()
    user_prompt = self._build_decision_prompt(nearby_tiles, tick, time_description,
                                              nearby_agents=nearby_agents or [])

    result = self.llm.generate_json(user_prompt, system_prompt=system_prompt)

    logger.debug(f"[{self.name}] LLM raw response: {result}")

    llm_trace = dict(self.llm.last_call) if self.llm.last_call else {}

    if result and "action" in result:
        logger.debug(f"[{self.name}] LLM decided: {result}")
        result["_llm_trace"] = llm_trace
        return result
    else:
        logger.warning(f"[{self.name}] LLM did not return a valid action, using fallback")
        fallback = self._fallback_decision(nearby_tiles)
        fallback["_llm_trace"] = llm_trace
        return fallback
```

**b) Update `_build_decision_prompt()` signature and body** (add `nearby_agents` parameter):

```python
def _build_decision_prompt(self, nearby_tiles: list[dict], tick: int,
                           time_description: str = "",
                           nearby_agents: list | None = None) -> str:
    ascii_grid = self._build_ascii_grid(nearby_tiles)
    _current_tile = next(
        (t["tile"] for t in nearby_tiles if t["x"] == self.x and t["y"] == self.y),
        "land",
    )
    current_tile_info = f"[Tile: {_current_tile}]"
    resource_hints = self._build_resource_hints(nearby_tiles)
    memory_text = self.get_recent_memory()

    if self.energy <= 0:
        status_effects = prompt_loader.load("agent/energy_critical")
    elif self.energy <= ENERGY_LOW_THRESHOLD:
        status_effects = prompt_loader.load("agent/energy_low")
    else:
        status_effects = ""

    inventory_info = self.inventory.to_prompt()
    nearby_agents_text = self.nearby_agents_prompt(nearby_agents or [])

    return prompt_loader.render(
        "agent/decision",
        tick=tick,
        life=self.life,
        max_life=AGENT_MAX_LIFE,
        hunger=self.hunger,
        max_hunger=AGENT_MAX_HUNGER,
        hunger_threshold=HUNGER_DAMAGE_THRESHOLD,
        energy=self.energy,
        max_energy=AGENT_MAX_ENERGY,
        ascii_grid=ascii_grid,
        resource_hints=resource_hints,
        memory_text=memory_text,
        status_effects=status_effects,
        time_info=time_description,
        inventory_info=inventory_info,
        current_tile_info=current_tile_info,
        nearby_agents=nearby_agents_text,
    )
```

### Step 5: Update `simulation/engine.py` — pass nearby agents to decide_action

In `_run_tick()`, find the block where `nearby` is gathered and `decide_action` is called (around line 139). Update it:

```python
# 1. Get environment perception (radius varies by time of day)
nearby = self.world.get_nearby_tiles(agent.x, agent.y, vision_radius)

# Gather nearby agents for social perception (same vision radius)
nearby_agent_list = self.world.get_agents_in_radius(
    agent, alive_agents, vision_radius
)
```

Then update the `decide_action` call (around line 150):
```python
# 2. Agent decides its action
action = agent.decide_action(nearby, tick, time_description,
                             nearby_agents=nearby_agent_list)
```

### Step 6: Run tests to verify they pass

```bash
uv run pytest tests/test_agent_prompts.py -v
```
Expected: all tests PASS including the 3 new ones.

```bash
uv run pytest -m "not slow" -q
```
Expected: ALL tests pass.

### Step 7: Smoke test

```bash
uv run main.py --no-llm --ticks 5 --agents 3
```
Expected: runs without errors. Console output normal.

### Step 8: Commit

```bash
git add prompts/agent/decision.txt simulation/agent.py simulation/engine.py tests/test_agent_prompts.py
git commit -m "feat(phase3a): wire social perception into decision prompt and engine"
```

---

## Verification

### Full test suite

```bash
uv run pytest -m "not slow" -v
```
Expected: all pass. New test files: `test_personality.py`, `test_perception.py`.

### Smoke test (no LLM)

```bash
uv run main.py --no-llm --ticks 10 --agents 3
```
Expected: runs cleanly, no exceptions, agents make decisions.

### Full LLM run (if Ollama available)

```bash
uv run main.py --agents 3 --ticks 10 --seed 42 --save-log --verbose
```
Check the saved log under `logs/` — open the latest run's markdown file and verify:
1. Each agent's system prompt contains a "Personality traits" line with their values
2. At least one tick shows `NEARBY AGENTS:` section in the decision prompt (agents must be near each other — may not always happen with random spawn)

To force agents near each other for testing, use a small world:
```bash
uv run main.py --agents 3 --ticks 5 --seed 42 --save-log
```
Then check `logs/<latest>/` for decision prompts with `NEARBY AGENTS`.

---

## Summary of Changes

| File | Type | Change |
|------|------|--------|
| `simulation/personality.py` | New | Personality dataclass with `random()` and `to_prompt()` |
| `simulation/agent.py` | Modified | Add `personality` field, `nearby_agents_prompt()`, update `decide_action` + `_build_decision_prompt` signatures |
| `simulation/world.py` | Modified | Add `get_agents_in_radius()` |
| `simulation/engine.py` | Modified | Gather nearby agents per tick, pass to `decide_action` |
| `prompts/agent/system.txt` | Modified | Add `$personality_description` variable |
| `prompts/agent/decision.txt` | Modified | Add `$nearby_agents` variable |
| `tests/test_personality.py` | New | 9 tests for Personality |
| `tests/test_perception.py` | New | 18 tests for social perception |
| `tests/test_agent_prompts.py` | Modified | +7 tests for personality + prompt wiring |
