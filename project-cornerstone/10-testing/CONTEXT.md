# 10 — Testing Strategy

## Current Status

**0 tests currently exist.** `pytest>=9.0.2` is declared in `pyproject.toml` but no test files have been written yet.

Priority order:
1. Unit tests (no LLM) — `test_world.py`, `test_agent.py`, `test_oracle.py`
2. MockLLM integration tests — `test_integration.py`
3. Behavioral tests (real LLM, slow) — `test_behavioral.py`

### MockLLM skeleton to implement

```python
# tests/conftest.py
class MockLLM:
    def __init__(self, responses: list[dict]):
        self._responses = iter(responses)

    def generate_json(self, *args, **kwargs) -> dict | None:
        return next(self._responses, {"action": "rest", "reason": "mock"})

    def generate(self, *args, **kwargs) -> str:
        import json
        return json.dumps(self.generate_json())

    def is_available(self) -> bool:
        return True
```

### First concrete unit tests to write

- **`test_world.py`**: generation determinism (same seed → same world), walkability (water not walkable), resource consumption reduces quantity
- **`test_agent.py`**: stat clamping (life/hunger/energy never out of [0, max]), memory cap at 50, dead agent `decide_action()` returns `{"action": "none", ...}`
- **`test_oracle.py`**: move into water fails (`success=False`), eat with no nearby food fails, same input → same precedent output (determinism)

---

## Philosophy

This project has an unusual enemy: **LLM non-determinism**. Most bugs won't be crashes but "dumb behavior". The testing strategy must reflect this.

## Testing layers

### Layer 1: Unit Tests (deterministic, no LLM)

```python
# tests/test_world.py
def test_world_generation_deterministic():
    """Same seed → same world"""
    w1 = World(seed=42)
    w2 = World(seed=42)
    assert w1.grid == w2.grid

def test_walkability():
    """Water is not walkable, land and trees are"""
    w = World(seed=42)
    # Find a water tile and verify
    for y in range(w.height):
        for x in range(w.width):
            if w.grid[y][x] == "water":
                assert not w.is_walkable(x, y)
                return

def test_resource_consumption():
    """Consuming resource reduces quantity"""
    w = World(seed=42)
    # Find a tree with fruit
    for (x, y), res in w.resources.items():
        initial = res["quantity"]
        consumed = w.consume_resource(x, y, 1)
        assert consumed == 1
        assert w.resources.get((x, y), {}).get("quantity", 0) == initial - 1
        return

# tests/test_agent.py
def test_agent_stats_bounds():
    """Stats never go below 0 or above maximum"""
    a = Agent(name="Test")
    a.modify_hunger(-999)
    assert a.hunger == 0
    a.modify_hunger(999)
    assert a.hunger == AGENT_MAX_HUNGER

def test_dead_agent_no_action():
    """Dead agent returns none action"""
    a = Agent(name="Test")
    a.alive = False
    result = a.decide_action([], 1)
    assert result["action"] == "none"

def test_memory_cap():
    """Memory doesn't exceed maximum"""
    a = Agent(name="Test")
    for i in range(100):
        a.add_memory(f"entry {i}")
    assert len(a.memory) == a.max_memory

# tests/test_oracle.py
def test_move_to_water_fails():
    """Moving to water returns success=false"""
    w = World(seed=42)
    o = Oracle(w)
    # Find agent next to water
    # ...
    
def test_eat_without_food_fails():
    """Eating without nearby food fails"""
    w = World(seed=42)
    a = Agent(name="Test", x=0, y=0)
    # Ensure there's no food at (0,0) or adjacent
    o = Oracle(w)
    result = o.resolve_action(a, {"action": "eat"}, 1)
    # May fail if there's food, use mock world

def test_precedent_determinism():
    """Same precedent → same result"""
    w = World(seed=42)
    o = Oracle(w)
    # Establish a precedent
    o.precedents["test_key"] = {"value": 42}
    # Verify it's reused
    assert o.precedents["test_key"]["value"] == 42
```

### Layer 2: Integration Tests (with mock LLM)

```python
# tests/conftest.py
class MockLLM:
    """LLM that returns predefined responses for testing"""
    
    def __init__(self, responses: list[dict]):
        self.responses = responses
        self.call_count = 0
    
    def generate_json(self, prompt, system_prompt="", temperature=0.7):
        if self.call_count < len(self.responses):
            result = self.responses[self.call_count]
            self.call_count += 1
            return result
        return {"action": "rest", "reason": "default"}
    
    def generate(self, prompt, system_prompt="", temperature=0.7):
        return json.dumps(self.generate_json(prompt, system_prompt, temperature))
    
    def is_available(self):
        return True


# tests/test_integration.py
def test_agent_survives_10_ticks():
    """An agent with access to food survives 10 ticks"""
    mock_responses = [
        {"action": "eat", "reason": "hungry"},
        {"action": "rest", "reason": "tired"},
        {"action": "move", "direction": "north", "reason": "explore"},
        # ... repeat pattern
    ]
    mock_llm = MockLLM(mock_responses * 10)
    engine = SimulationEngine(num_agents=1, world_seed=42, use_llm=True)
    # Inject mock LLM
    for agent in engine.agents:
        agent.llm = mock_llm
    engine.oracle.llm = mock_llm
    engine.run()
    assert engine.agents[0].alive
```

### Layer 3: Behavioral Tests (with real LLM, statistical)

```python
# tests/test_behavioral.py  (slow, require Ollama running)
import pytest

@pytest.mark.slow
@pytest.mark.requires_ollama
def test_agent_decisions_coherent():
    """At least 80% of decisions are coherent in 30 ticks"""
    engine = SimulationEngine(num_agents=1, world_seed=42, max_ticks=30)
    engine.run()
    
    # Analyze log: how many times did agent eat when hunger was high?
    # how many times did it rest when energy was low?
    # Define "coherent" as: reasonable action given the state
    coherent = count_coherent_decisions(engine)
    total = len(engine.oracle.world_log)
    assert coherent / total > 0.8

@pytest.mark.slow
def test_innovation_never_approves_magic():
    """The oracle never approves magical actions"""
    # Force agent to try innovating "fly" or "teleport"
    # Verify oracle rejects them
```

## Herramientas

```bash
# Run all fast tests
pytest tests/ -m "not slow"

# Run with coverage
pytest tests/ --cov=simulation --cov-report=html

# Run behavioral tests (requires Ollama)
pytest tests/ -m slow --timeout=300

# Run specific test
pytest tests/test_world.py::test_world_generation_deterministic -v
```

## pytest.ini

```ini
[pytest]
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    requires_ollama: marks tests that need Ollama running
testpaths = tests
```

## Considerations for Claude Code

- ALWAYS run `pytest -m "not slow"` before committing.
- New features MUST come with unit tests at minimum.
- MockLLM is the most important tool for testing. Keep it updated.
- Coverage target: >80% in core modules (world, agent, oracle), >60% overall.
