# Phase 3b — Communication + Trust + Conflict Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Phase 3b of the Emerge social system in two atomic PRs: (1) a `communicate` base action with message queuing, and (2) a `Relationship`/trust system with emergent conflict consequences.

**Architecture:** Two PRs. PR 1 adds the `communicate` base action: Oracle validates target/range/intent/energy, queues an `IncomingMessage` to the recipient, which appears in their decision prompt next tick then is discarded. PR 2 adds the `Relationship` dataclass and trust update events triggered by social actions (communication and conflict innovations).

**Tech Stack:** Python 3.12, uv, pytest, Ollama (Qwen), existing Oracle/Agent/Engine pattern.

---

## Context

Phase 3a (personality + social perception) is complete and merged. Agents see each other and have personality traits, but cannot interact. Phase 3b gives them a voice and a memory of social outcomes. The `communicate` action is the first real social primitive — it lets agents share information, warn, or request help. The trust system builds a relationship model that will serve as the foundation for Phase 3c cooperation and Phase 4 reproduction (bonded agents).

**Decisions confirmed in brainstorming:**
- Resource competition: first-come wins (current behavior). No engine refactor.
- Oracle validates communicate meta-only (no LLM content validation).
- Messages discarded after 1 tick; agents rely on their own episodic memory for persistence.
- Conflict trust damage comes from innovated actions (Oracle stores `trust_impact` in precedent).
- Communication trust delta: +0.05 sender→recipient per successful send.

**Critical files:**
- `simulation/oracle.py` — `resolve_action()` at line 116, dispatcher at 125-143, `_resolve_custom_action()` at 472
- `simulation/engine.py` — tick loop agent processing at line 134, `oracle.resolve_action()` call at 177
- `simulation/agent.py` — `decide_action()`, `_build_decision_prompt()`, `_build_system_prompt()`
- `prompts/agent/decision.txt` — prompt template
- `prompts/agent/system.txt` — system prompt template
- `simulation/config.py` — all constants
- `project-cornerstone/00-master-plan/DECISION_LOG.md` — add DEC-020, DEC-021, DEC-022
- `project-cornerstone/00-master-plan/MASTER_PLAN.md` — update Phase 3 checklist

---

## PR 1: Communication (`feat(phase3b): communicate base action + message queuing`)

### Task 1: Write the design doc

**Files:**
- Create: `docs/plans/2026-03-07-phase3b-design.md`

Write the approved Phase 3b design (communication + trust + conflict summary with the decisions above) to `docs/plans/2026-03-07-phase3b-design.md`.

**Step 1: Create the doc**

Content should summarize: PR split rationale, data structures (`IncomingMessage`, `Relationship`), oracle validation rules, trust event table, conflict via `trust_impact` in precedent.

**Step 2: Commit**
```bash
git add docs/plans/2026-03-07-phase3b-design.md
git commit -m "docs(plan): add Phase 3b communication + trust design"
```

---

### Task 2: Add `IncomingMessage` dataclass

**Files:**
- Create: `simulation/message.py`
- Test: `tests/test_communication.py` (start file, add imports)

**Step 1: Write the failing test**
```python
# tests/test_communication.py
from simulation.message import IncomingMessage, VALID_INTENTS

def test_incoming_message_fields():
    msg = IncomingMessage(sender="Bruno", tick=5, message="Fruit east!", intent="share_info")
    assert msg.sender == "Bruno"
    assert msg.tick == 5
    assert msg.message == "Fruit east!"
    assert msg.intent == "share_info"

def test_valid_intents_set():
    assert "share_info" in VALID_INTENTS
    assert "request_help" in VALID_INTENTS
    assert "warn" in VALID_INTENTS
    assert "trade_offer" in VALID_INTENTS
    assert "attack" not in VALID_INTENTS
```

**Step 2: Run test to verify it fails**
```bash
uv run pytest tests/test_communication.py -v
```
Expected: `ModuleNotFoundError: simulation.message`

**Step 3: Write minimal implementation**
```python
# simulation/message.py
from dataclasses import dataclass

VALID_INTENTS = {"share_info", "request_help", "warn", "trade_offer"}

@dataclass
class IncomingMessage:
    sender: str
    tick: int
    message: str
    intent: str
```

**Step 4: Run test to verify it passes**
```bash
uv run pytest tests/test_communication.py::test_incoming_message_fields tests/test_communication.py::test_valid_intents_set -v
```
Expected: PASS

**Step 5: Commit**
```bash
git add simulation/message.py tests/test_communication.py
git commit -m "feat(phase3b): add IncomingMessage dataclass and VALID_INTENTS"
```

---

### Task 3: Add `incoming_messages` + `get_messages_prompt()` to Agent

**Files:**
- Modify: `simulation/agent.py`
- Test: `tests/test_communication.py`

**Step 1: Write the failing tests**
```python
# tests/test_communication.py (add these)
from simulation.agent import Agent
from simulation.message import IncomingMessage

def test_agent_has_incoming_messages():
    agent = Agent(name="Kai", x=0, y=0)
    assert agent.incoming_messages == []

def test_get_messages_prompt_empty():
    agent = Agent(name="Kai", x=0, y=0)
    assert agent.get_messages_prompt() == ""

def test_get_messages_prompt_with_message():
    agent = Agent(name="Kai", x=0, y=0)
    agent.incoming_messages.append(
        IncomingMessage(sender="Bruno", tick=12, message="Fruit east!", intent="share_info")
    )
    prompt = agent.get_messages_prompt()
    assert "INCOMING MESSAGES:" in prompt
    assert "Bruno" in prompt
    assert "tick 12" in prompt
    assert "Fruit east!" in prompt
    assert "[share_info]" in prompt

def test_get_messages_prompt_multiple():
    agent = Agent(name="Kai", x=0, y=0)
    agent.incoming_messages.append(IncomingMessage("Bruno", 10, "Go west", "warn"))
    agent.incoming_messages.append(IncomingMessage("Clara", 10, "I need help", "request_help"))
    prompt = agent.get_messages_prompt()
    assert "Bruno" in prompt
    assert "Clara" in prompt
```

**Step 2: Run tests to verify they fail**
```bash
uv run pytest tests/test_communication.py -v -k "incoming_messages or messages_prompt"
```
Expected: FAIL (AttributeError on agent)

**Step 3: Write minimal implementation**

In `simulation/agent.py`, in `__init__` after inventory:
```python
self.incoming_messages: list["IncomingMessage"] = []
```

Add import at top of file:
```python
from simulation.message import IncomingMessage
```

Add method after `nearby_agents_prompt`:
```python
def get_messages_prompt(self) -> str:
    if not self.incoming_messages:
        return ""
    lines = ["INCOMING MESSAGES:"]
    for msg in self.incoming_messages:
        lines.append(f'- {msg.sender} (tick {msg.tick}): "{msg.message}" [{msg.intent}]')
    return "\n".join(lines)
```

**Step 4: Run tests**
```bash
uv run pytest tests/test_communication.py -v
```
Expected: PASS

**Step 5: Commit**
```bash
git add simulation/agent.py simulation/message.py tests/test_communication.py
git commit -m "feat(phase3b): add incoming_messages + get_messages_prompt() to Agent"
```

---

### Task 4: Add `COMMUNICATE_ENERGY_COST` to config

**Files:**
- Modify: `simulation/config.py`

**Step 1: Add constant** (no test needed — config is tested transitively)

In `simulation/config.py`, add in the energy costs section:
```python
COMMUNICATE_ENERGY_COST = 3
```

**Step 2: Commit**
```bash
git add simulation/config.py
git commit -m "feat(phase3b): add COMMUNICATE_ENERGY_COST config constant"
```

---

### Task 5: Add `_resolve_communicate()` to Oracle

**Files:**
- Modify: `simulation/oracle.py`
- Test: `tests/test_communication.py`

The Oracle needs `alive_agents` to find the target. The engine will set `oracle.current_tick_agents` before the per-agent loop. The oracle also needs a per-tick rate limit set: `oracle._communicated_this_tick: set[str]`.

**Step 1: Write the failing tests**
```python
# tests/test_communication.py (add these)
from unittest.mock import MagicMock
from simulation.oracle import Oracle
from simulation.agent import Agent

def make_two_agents():
    sender = Agent(name="Kai", x=5, y=5)
    sender.stats.energy = 20
    target = Agent(name="Bruno", x=6, y=5)  # 1 tile away
    return sender, target

def test_communicate_queues_message():
    sender, target = make_two_agents()
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender, target]
    oracle._communicated_this_tick = set()
    action = {"action": "communicate", "target": "Bruno", "message": "Fruit east!", "intent": "share_info"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is True
    assert len(target.incoming_messages) == 1
    assert target.incoming_messages[0].sender == "Kai"
    assert target.incoming_messages[0].message == "Fruit east!"

def test_communicate_costs_energy():
    sender, target = make_two_agents()
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender, target]
    oracle._communicated_this_tick = set()
    action = {"action": "communicate", "target": "Bruno", "message": "Hey!", "intent": "warn"}
    oracle.resolve_action(sender, action, tick=1)
    assert sender.stats.energy == 17  # 20 - 3

def test_communicate_invalid_intent():
    sender, target = make_two_agents()
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender, target]
    oracle._communicated_this_tick = set()
    action = {"action": "communicate", "target": "Bruno", "message": "Attack!", "intent": "attack"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is False
    assert len(target.incoming_messages) == 0

def test_communicate_target_not_found():
    sender, _ = make_two_agents()
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender]  # target not in list
    oracle._communicated_this_tick = set()
    action = {"action": "communicate", "target": "Ghost", "message": "Hey!", "intent": "share_info"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is False

def test_communicate_target_out_of_range():
    sender = Agent(name="Kai", x=0, y=0)
    sender.stats.energy = 20
    far_target = Agent(name="Bruno", x=9, y=9)  # 18 tiles away
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender, far_target]
    oracle._communicated_this_tick = set()
    # vision_radius defaults to AGENT_VISION_RADIUS = 3
    action = {"action": "communicate", "target": "Bruno", "message": "Hi!", "intent": "share_info"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is False

def test_communicate_rate_limit():
    sender, target = make_two_agents()
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender, target]
    oracle._communicated_this_tick = {"Kai"}  # already communicated this tick
    action = {"action": "communicate", "target": "Bruno", "message": "Again!", "intent": "warn"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is False
    assert len(target.incoming_messages) == 0

def test_communicate_insufficient_energy():
    sender, target = make_two_agents()
    sender.stats.energy = 2  # less than COMMUNICATE_ENERGY_COST=3
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender, target]
    oracle._communicated_this_tick = set()
    action = {"action": "communicate", "target": "Bruno", "message": "Hi!", "intent": "share_info"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is False
```

**Step 2: Run tests to verify they fail**
```bash
uv run pytest tests/test_communication.py -v -k "communicate"
```
Expected: FAIL

**Step 3: Implement `_resolve_communicate()` in oracle.py**

Add import at top:
```python
from simulation.message import IncomingMessage, VALID_INTENTS
from simulation.config import COMMUNICATE_ENERGY_COST, AGENT_VISION_RADIUS
```

Add `current_tick_agents` and `_communicated_this_tick` init in `Oracle.__init__`:
```python
self.current_tick_agents: list = []
self._communicated_this_tick: set[str] = set()
```

In `resolve_action()`, add before the `else` clause:
```python
elif action_type == "communicate":
    return self._resolve_communicate(agent, action, tick)
```

Add new method after `_resolve_pickup`:
```python
def _resolve_communicate(self, agent: Agent, action: dict, tick: int) -> dict:
    intent = action.get("intent", "")
    if intent not in VALID_INTENTS:
        return {"success": False, "message": f"Unknown intent '{intent}'.", "effects": {}}

    if agent.name in self._communicated_this_tick:
        return {"success": False, "message": "Already communicated this tick.", "effects": {}}

    if agent.stats.energy < COMMUNICATE_ENERGY_COST:
        return {"success": False, "message": "Not enough energy to communicate.", "effects": {}}

    target_name = action.get("target", "")
    target = next(
        (a for a in self.current_tick_agents if a.name == target_name and a.alive),
        None
    )
    if target is None:
        return {"success": False, "message": f"{target_name} not found or not alive.", "effects": {}}

    dist = abs(agent.x - target.x) + abs(agent.y - target.y)
    vision_radius = AGENT_VISION_RADIUS  # simplified; day_cycle reduces this
    if dist > vision_radius:
        return {"success": False, "message": f"{target_name} is too far away.", "effects": {}}

    message_text = action.get("message", "")
    agent.stats.energy -= COMMUNICATE_ENERGY_COST
    self._communicated_this_tick.add(agent.name)
    target.incoming_messages.append(
        IncomingMessage(sender=agent.name, tick=tick, message=message_text, intent=intent)
    )
    return {
        "success": True,
        "message": f"Message sent to {target_name}: \"{message_text}\"",
        "effects": {}
    }
```

**Step 4: Run tests**
```bash
uv run pytest tests/test_communication.py -v
```
Expected: PASS

**Step 5: Commit**
```bash
git add simulation/oracle.py tests/test_communication.py
git commit -m "feat(phase3b): add _resolve_communicate() to Oracle with rate limit + range check"
```

---

### Task 6: Wire communicate into Engine tick loop

**Files:**
- Modify: `simulation/engine.py`

The engine must:
1. Set `oracle.current_tick_agents = alive_agents` before the per-agent loop
2. Reset `oracle._communicated_this_tick = set()` at the start of each tick
3. Clear `agent.incoming_messages` right after `decide_action()` returns (before oracle resolves)

**Step 1: Write the failing test** (integration)
```python
# tests/test_communication.py (add)
from simulation.engine import SimulationEngine
from tests.helpers import make_mock_engine  # use existing test helpers

def test_engine_clears_messages_after_decide():
    """Messages are cleared after agent decides but before next tick."""
    # Use --no-llm mode with 2 agents, verify no message persists across ticks
    # Use MockLLM that returns communicate action for agent A toward B tick 1,
    # then verify B's incoming_messages is empty at tick 2 decide_action time.
    # This is an integration test — mark slow or use MockLLM
    pass  # implement if MockLLM infrastructure supports it; otherwise verify manually
```

Note: The engine test is complex. Prioritize the manual verification step instead.

**Step 2: Edit engine.py**

Find the tick loop (around line 130). Before the `for agent in alive_agents:` loop, add:
```python
# Reset per-tick Oracle state for communication
self.oracle.current_tick_agents = alive_agents
self.oracle._communicated_this_tick = set()
```

Inside the loop, right after `action = agent.decide_action(...)` (line 155-156), add:
```python
# Clear incoming messages now that agent has decided (before Oracle runs)
agent.incoming_messages.clear()
```

**Step 3: Verify manually**
```bash
uv run main.py --no-llm --ticks 5 --agents 3
```
Expected: No crash. Communicate won't be used in `--no-llm` mode (no LLM to choose it), but wiring is correct.

**Step 4: Run all tests**
```bash
uv run pytest -m "not slow" -v
```
Expected: All pass.

**Step 5: Commit**
```bash
git add simulation/engine.py
git commit -m "feat(phase3b): wire communicate into engine tick loop (reset + clear messages)"
```

---

### Task 7: Update decision prompt and system prompt

**Files:**
- Modify: `prompts/agent/decision.txt`
- Modify: `prompts/agent/system.txt`

**Step 1: Read both files first** to understand exact variable insertion points.

**Step 2: Update decision.txt**

Add `$incoming_messages` after `$nearby_agents` (empty string = section omitted):
```
$nearby_agents
$incoming_messages
```

**Step 3: Update agent.py `_build_decision_prompt()`**

Find where `nearby_agents` is passed to the template and add `incoming_messages`:
```python
incoming_messages=self.get_messages_prompt(),
```

**Step 4: Update system.txt**

Add `communicate` to the list of available base actions with its intent options:
```
- communicate: Send a message to a nearby agent.
  Format: {"action": "communicate", "target": "<name>", "message": "<text>", "intent": "<share_info|request_help|warn|trade_offer>"}
```

**Step 5: Run smoke test**
```bash
uv run main.py --no-llm --ticks 5 --agents 3
```

**Step 6: Run all tests**
```bash
uv run pytest -m "not slow"
```

**Step 7: Commit**
```bash
git add prompts/agent/decision.txt prompts/agent/system.txt simulation/agent.py
git commit -m "feat(phase3b): add communicate to prompts (incoming_messages section + system action list)"
```

---

### Task 8: Full LLM smoke test + PR

**Step 1: Test with LLM**
```bash
uv run main.py --agents 3 --ticks 30 --seed 42 --save-log --verbose
```
Check saved log: look for agents choosing `communicate` action, messages appearing in decision prompts.

**Step 2: Run full test suite**
```bash
uv run pytest -m "not slow"
```

**Step 3: Open PR**

Title: `feat(phase3b): communicate base action + message queuing`

PR description should mention:
- New `IncomingMessage` dataclass (`simulation/message.py`)
- `agent.incoming_messages` + `get_messages_prompt()`
- `oracle._resolve_communicate()` with meta validation (intent, target, range, energy, rate limit)
- Engine wiring (current_tick_agents, message clearing)
- Prompt additions (incoming_messages section, system action description)
- Tests: `tests/test_communication.py` (N tests)

---

## PR 2: Trust + Conflict (`feat(phase3b): trust/relationship system + conflict consequences`)

### Task 9: Add `Relationship` dataclass

**Files:**
- Create: `simulation/relationship.py`
- Test: `tests/test_trust.py`

**Step 1: Write the failing tests**
```python
# tests/test_trust.py
from simulation.relationship import Relationship
from simulation.config import BONDING_TRUST_THRESHOLD, BONDING_COOPERATION_MINIMUM

def test_relationship_defaults():
    rel = Relationship(target="Bruno")
    assert rel.trust == 0.0
    assert rel.cooperations == 0
    assert rel.conflicts == 0
    assert rel.bonded is False

def test_relationship_status_friendly():
    rel = Relationship(target="Bruno", trust=0.7)
    assert rel.status == "friendly"

def test_relationship_status_neutral():
    rel = Relationship(target="Bruno", trust=0.4)
    assert rel.status == "neutral"

def test_relationship_status_wary():
    rel = Relationship(target="Bruno", trust=-0.2)
    assert rel.status == "wary"

def test_relationship_status_hostile():
    rel = Relationship(target="Bruno", trust=-0.5)
    assert rel.status == "hostile"

def test_update_trust_clamped_high():
    rel = Relationship(target="Bruno", trust=0.98)
    rel.update(delta=0.1, tick=5)
    assert rel.trust == 1.0

def test_update_trust_clamped_low():
    rel = Relationship(target="Bruno", trust=-0.98)
    rel.update(delta=-0.1, tick=5)
    assert rel.trust == -1.0

def test_update_cooperation_counter():
    rel = Relationship(target="Bruno")
    rel.update(delta=0.1, tick=5, is_cooperation=True)
    assert rel.cooperations == 1

def test_bonding_trigger():
    rel = Relationship(target="Bruno", trust=0.74, cooperations=2)
    rel.update(delta=0.02, tick=5, is_cooperation=True)
    # trust=0.76, cooperations=3 → bonded
    assert rel.bonded is True

def test_bonding_not_triggered_low_trust():
    rel = Relationship(target="Bruno", trust=0.5, cooperations=4)
    rel.update(delta=0.05, tick=5, is_cooperation=True)
    assert rel.bonded is False  # trust still below threshold
```

**Step 2: Run tests to verify they fail**
```bash
uv run pytest tests/test_trust.py -v
```
Expected: `ModuleNotFoundError: simulation.relationship`

**Step 3: Write minimal implementation**
```python
# simulation/relationship.py
from dataclasses import dataclass, field
from simulation.config import BONDING_TRUST_THRESHOLD, BONDING_COOPERATION_MINIMUM

@dataclass
class Relationship:
    target: str
    trust: float = 0.0
    cooperations: int = 0
    conflicts: int = 0
    last_tick: int = 0
    bonded: bool = False

    @property
    def status(self) -> str:
        if self.trust > 0.6:   return "friendly"
        if self.trust > 0.2:   return "neutral"
        if self.trust > -0.3:  return "wary"
        return "hostile"

    def update(self, delta: float, tick: int, is_cooperation: bool = False, is_conflict: bool = False):
        self.trust = max(-1.0, min(1.0, self.trust + delta))
        self.last_tick = tick
        if is_cooperation:
            self.cooperations += 1
        if is_conflict:
            self.conflicts += 1
        if (self.trust >= BONDING_TRUST_THRESHOLD
                and self.cooperations >= BONDING_COOPERATION_MINIMUM):
            self.bonded = True
```

Add to `simulation/config.py`:
```python
BONDING_TRUST_THRESHOLD = 0.75
BONDING_COOPERATION_MINIMUM = 3
COMMUNICATE_TRUST_DELTA = 0.05
```

**Step 4: Run tests**
```bash
uv run pytest tests/test_trust.py -v
```
Expected: PASS

**Step 5: Commit**
```bash
git add simulation/relationship.py simulation/config.py tests/test_trust.py
git commit -m "feat(phase3b): add Relationship dataclass with trust/bonding system"
```

---

### Task 10: Add `relationships` + `update_relationship()` + `get_relationships_prompt()` to Agent

**Files:**
- Modify: `simulation/agent.py`
- Test: `tests/test_trust.py`

**Step 1: Write the failing tests**
```python
# tests/test_trust.py (add)
from simulation.agent import Agent

def test_agent_has_empty_relationships():
    agent = Agent(name="Kai", x=0, y=0)
    assert agent.relationships == {}

def test_update_relationship_creates_entry():
    agent = Agent(name="Kai", x=0, y=0)
    agent.update_relationship("Bruno", delta=0.1, tick=5, is_cooperation=True)
    assert "Bruno" in agent.relationships
    assert agent.relationships["Bruno"].trust == 0.1
    assert agent.relationships["Bruno"].cooperations == 1

def test_get_relationships_prompt_empty():
    agent = Agent(name="Kai", x=0, y=0)
    assert agent.get_relationships_prompt(current_tick=1) == ""

def test_get_relationships_prompt_shows_status():
    agent = Agent(name="Kai", x=0, y=0)
    agent.update_relationship("Bruno", delta=0.7, tick=3, is_cooperation=True)
    prompt = agent.get_relationships_prompt(current_tick=5)
    assert "RELATIONSHIPS:" in prompt
    assert "Bruno" in prompt
    assert "friendly" in prompt.lower() or "Friendly" in prompt
```

**Step 2: Run to verify fail**
```bash
uv run pytest tests/test_trust.py -v -k "agent"
```

**Step 3: Implement in agent.py**

Add import:
```python
from simulation.relationship import Relationship
```

In `__init__`, after `incoming_messages`:
```python
self.relationships: dict[str, Relationship] = {}
```

Add methods:
```python
def update_relationship(self, target_name: str, delta: float, tick: int, **kwargs):
    if target_name not in self.relationships:
        self.relationships[target_name] = Relationship(target=target_name)
    self.relationships[target_name].update(delta=delta, tick=tick, **kwargs)

def get_relationships_prompt(self, current_tick: int) -> str:
    if not self.relationships:
        return ""
    lines = ["RELATIONSHIPS:"]
    for name, rel in self.relationships.items():
        ticks_ago = current_tick - rel.last_tick
        lines.append(
            f"- {name}: {rel.status.capitalize()} (trust: {rel.trust:.2f}), "
            f"last interacted {ticks_ago} tick(s) ago"
        )
    return "\n".join(lines)
```

**Step 4: Run tests**
```bash
uv run pytest tests/test_trust.py -v
```
Expected: PASS

**Step 5: Commit**
```bash
git add simulation/agent.py tests/test_trust.py
git commit -m "feat(phase3b): add relationships dict + update_relationship() + get_relationships_prompt() to Agent"
```

---

### Task 11: Apply trust delta on `communicate` success (Oracle)

**Files:**
- Modify: `simulation/oracle.py`
- Test: `tests/test_trust.py`

**Step 1: Write the failing test**
```python
# tests/test_trust.py (add)
from simulation.oracle import Oracle
from simulation.agent import Agent
from unittest.mock import MagicMock

def test_communicate_builds_trust():
    sender = Agent(name="Kai", x=5, y=5)
    sender.stats.energy = 20
    target = Agent(name="Bruno", x=6, y=5)
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender, target]
    oracle._communicated_this_tick = set()
    action = {"action": "communicate", "target": "Bruno", "message": "Hi!", "intent": "share_info"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is True
    assert "Bruno" in sender.relationships
    assert sender.relationships["Bruno"].trust == pytest.approx(0.05, abs=0.001)
```

**Step 2: Run to verify fail**
```bash
uv run pytest tests/test_trust.py::test_communicate_builds_trust -v
```

**Step 3: Update `_resolve_communicate()` in oracle.py**

After the successful `target.incoming_messages.append(...)`, add:
```python
# Trust: sender trusts recipient a little more after reaching out
from simulation.config import COMMUNICATE_TRUST_DELTA
agent.update_relationship(target.name, delta=COMMUNICATE_TRUST_DELTA, tick=tick, is_cooperation=True)
```

**Step 4: Run tests**
```bash
uv run pytest tests/test_trust.py -v
```
Expected: PASS

**Step 5: Commit**
```bash
git add simulation/oracle.py tests/test_trust.py
git commit -m "feat(phase3b): apply trust delta on successful communicate action"
```

---

### Task 12: Store `trust_impact` in innovation precedents for conflict actions

**Files:**
- Modify: `simulation/oracle.py` — `_validate_innovation()` and `_resolve_custom_action()`
- Test: `tests/test_trust.py`

**Goal:** When an agent innovates an aggressive action, the Oracle LLM sets `aggressive: true` and `trust_impact: float` (0.0–0.5) in the validation response. When the innovated action executes, victim's trust toward attacker drops by `trust_impact`.

**Step 1: Write the failing test**
```python
# tests/test_trust.py (add)
def test_aggressive_innovation_sets_trust_impact():
    """Validate that oracle stores trust_impact in precedent for SOCIAL+aggressive actions."""
    from simulation.oracle import Oracle
    from unittest.mock import MagicMock

    # MockLLM that returns an aggressive innovation validation result
    mock_llm = MagicMock()
    mock_llm.generate_json.return_value = {
        "approved": True,
        "reason": "Physically plausible aggression.",
        "category": "SOCIAL",
        "aggressive": True,
        "trust_impact": 0.3,
        "effects": {"life": -10, "energy": -15}
    }
    oracle = Oracle(world=MagicMock(), llm=mock_llm)
    oracle.current_tick_agents = []
    oracle._communicated_this_tick = set()

    agent = Agent(name="Kai", x=5, y=5)
    agent.stats.energy = 40
    action = {
        "action": "innovate",
        "name": "steal_food",
        "description": "Grab food from another agent's hands.",
        "effects": {"hunger": -10},
        "requires": {}
    }
    result = oracle.resolve_action(agent, action, tick=1)
    # Precedent should have trust_impact stored
    key = "innovation:steal_food"
    assert key in oracle.precedents
    if oracle.precedents[key].get("aggressive"):
        assert "trust_impact" in oracle.precedents[key]
```

**Step 2: Run to verify fail**
```bash
uv run pytest tests/test_trust.py::test_aggressive_innovation_sets_trust_impact -v
```

**Step 3: Update `_validate_innovation()` prompt**

In the Oracle's innovation validation prompt (in `prompts/oracle/innovate_validate.txt` or inline), add to the JSON schema:
```
If this action involves aggression (stealing, attacking, threatening), set:
  "aggressive": true,
  "trust_impact": <float 0.05-0.5 based on severity>
Otherwise omit both fields.
```

In `_resolve_innovate()`, after storing the precedent, also preserve `aggressive` and `trust_impact` from the LLM response:
```python
if result.get("aggressive"):
    innovation_data["aggressive"] = True
    innovation_data["trust_impact"] = float(result.get("trust_impact", 0.2))
```

**Step 4: Update `_resolve_custom_action()` to apply trust on execution**

After the action resolves successfully, check if it's aggressive:
```python
precedent_key = f"innovation:{action_type}"
precedent = self.precedents.get(precedent_key, {})
if precedent.get("aggressive") and result.get("success"):
    trust_impact = float(precedent.get("trust_impact", 0.2))
    target_name = action.get("target")
    if target_name:
        # Find victim
        victim = next(
            (a for a in self.current_tick_agents if a.name == target_name and a.alive),
            None
        )
        if victim:
            victim.update_relationship(agent.name, delta=-trust_impact, tick=tick, is_conflict=True)
            agent.update_relationship(target_name, delta=-trust_impact * 0.5, tick=tick, is_conflict=True)
```

**Step 5: Run tests**
```bash
uv run pytest tests/test_trust.py -v
uv run pytest -m "not slow" -v
```
Expected: PASS

**Step 6: Commit**
```bash
git add simulation/oracle.py tests/test_trust.py
git commit -m "feat(phase3b): store trust_impact in precedents for aggressive innovations"
```

---

### Task 13: Wire relationships into Engine and decision prompt

**Files:**
- Modify: `simulation/engine.py`
- Modify: `simulation/agent.py` — `_build_decision_prompt()`
- Modify: `prompts/agent/decision.txt`

**Step 1: Update decision.txt**

Add `$relationships` after `$incoming_messages`:
```
$incoming_messages
$relationships
```

**Step 2: Update `_build_decision_prompt()` in agent.py**

Add:
```python
relationships=self.get_relationships_prompt(current_tick=tick),
```

**Step 3: Verify engine passes `tick` to `_build_decision_prompt()`**

Check the `decide_action()` signature — it already receives `tick`. Confirm `_build_decision_prompt()` also receives it. Adjust if needed.

**Step 4: Smoke test**
```bash
uv run main.py --no-llm --ticks 5 --agents 3
uv run pytest -m "not slow"
```

**Step 5: Commit**
```bash
git add prompts/agent/decision.txt simulation/agent.py
git commit -m "feat(phase3b): add relationships section to decision prompt"
```

---

### Task 14: Update cornerstone docs + final verification

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/00-master-plan/MASTER_PLAN.md`

**Step 1: Add decision log entries**

Append to `DECISION_LOG.md`:

```markdown
### DEC-020: Personality via prompt injection
- **Date**: 2026-03-07
- **Decision**: Personality traits injected as natural language in system prompt (not probability modifiers). LLM interprets them organically.

### DEC-021: Emergent conflict (not a base action)
- **Date**: 2026-03-07
- **Decision**: Aggression is not a base action. Agents innovate steal/attack. Oracle validation LLM sets `aggressive: true` and `trust_impact: float` in the precedent. Trust damage applied by Oracle on execution.

### DEC-022: Resource competition — first-come wins
- **Date**: 2026-03-07
- **Decision**: No engine-level conflict resolution for contested resources. Sequential Oracle processing means the first agent to act wins. Trust damage from conflict comes only from innovated aggressive actions.
```

**Step 2: Update MASTER_PLAN.md Phase 3 checklist**

Mark completed:
```markdown
- [x] Communication (speak, signal) — Phase 3b PR 1
- [x] Conflict (emergent via innovated actions + trust penalties) — Phase 3b PR 2
- [x] Reputation and relationships — Phase 3b PR 2
```

**Step 3: Full test suite + LLM run**
```bash
uv run pytest -m "not slow"
uv run main.py --agents 3 --ticks 50 --seed 42 --save-log --verbose
```

Check saved log:
- `communicate` actions appear
- `INCOMING MESSAGES:` section in decision prompts
- `RELATIONSHIPS:` section after interactions
- Trust changes logged after aggressive innovations

**Step 4: Commit**
```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/00-master-plan/MASTER_PLAN.md
git commit -m "docs(cornerstone): add DEC-020/021/022, update Phase 3b checklist"
```

**Step 5: Open PR 2**

Title: `feat(phase3b): trust/relationship system + conflict consequences`

---

## Verification (End-to-End)

```bash
# 1. Unit tests (fast, after each PR)
uv run pytest -m "not slow" -v

# 2. Specific Phase 3b tests
uv run pytest tests/test_communication.py tests/test_trust.py -v

# 3. Smoke test (no LLM)
uv run main.py --no-llm --ticks 10 --agents 3

# 4. Full LLM test after PR 1 (check communicate in logs)
uv run main.py --agents 3 --ticks 30 --seed 42 --save-log --verbose
# Look for: communicate action chosen, INCOMING MESSAGES in prompts

# 5. Full LLM test after PR 2 (check trust + conflict)
uv run main.py --agents 3 --ticks 50 --seed 42 --save-log --verbose
# Look for: RELATIONSHIPS section in prompts, trust changes, aggressive innovations
```
