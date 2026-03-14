# Agent Long-Term Planning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add explicit planner state, deterministic memory retrieval, and planner/executor orchestration so agents can persist and execute multi-tick plans instead of deciding from scratch every tick.

**Architecture:** Keep the current Oracle and world mutation model intact. Add a new `PlanningState` runtime object, a deterministic retrieval layer, and a separate planner prompt/module that runs on cadence or trigger conditions, while the existing decision step becomes an executor that advances the active subgoal. Emit planning events so the runtime can measure subgoal formation and completion instead of treating planning as invisible prompt text.

**Tech Stack:** Python 3, dataclasses, Pydantic v2 structured outputs, pytest, string.Template prompt files, JSONL event emitter

---

## Preconditions

- Work in a clean feature branch or worktree before implementing this plan.
- Do not overwrite unrelated local changes in `project-cornerstone/`.
- Keep `ENABLE_EXPLICIT_PLANNING` behind a feature flag until the full flow passes targeted and full tests.

### Task 1: Add Planning Config, Schemas, And Runtime State

**Files:**
- Create: `simulation/planning_state.py`
- Modify: `simulation/config.py`
- Modify: `simulation/schemas.py`
- Test: `tests/test_planning_state.py`

**Step 1: Write the failing tests**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_planning_state.py -v`

Expected: FAIL with `ModuleNotFoundError` for `simulation.planning_state` and missing `AgentPlanResponse`.

**Step 3: Write minimal implementation**

```python
# simulation/config.py
ENABLE_EXPLICIT_PLANNING = False
PLAN_REFRESH_INTERVAL = 5
TASK_MEMORY_MAX = 12
PLANNER_CONTEXT_MAX = 6
EXECUTOR_CONTEXT_MAX = 4


# simulation/schemas.py
class PlanSubgoalResponse(BaseModel):
    description: str
    kind: str
    target: Optional[str] = None
    preconditions: list[str] = []
    completion_signal: str
    failure_signal: str
    priority: int = 1


class AgentPlanResponse(BaseModel):
    goal: str
    goal_type: str
    subgoals: list[PlanSubgoalResponse]
    horizon: str
    success_signals: list[str]
    abort_conditions: list[str]
    confidence: float
    rationale_summary: str


# simulation/planning_state.py
from dataclasses import dataclass, field


@dataclass
class PlanningSubgoal:
    description: str
    kind: str
    target: str | None = None
    preconditions: list[str] = field(default_factory=list)
    completion_signal: str = ""
    failure_signal: str = ""
    priority: int = 1


@dataclass
class PlanningState:
    goal: str
    goal_type: str
    subgoals: list[PlanningSubgoal]
    active_subgoal_index: int
    status: str
    created_tick: int
    last_plan_tick: int
    last_progress_tick: int
    confidence: float
    horizon: str
    success_signals: list[str] = field(default_factory=list)
    abort_conditions: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    rationale_summary: str = ""

    @classmethod
    def empty(cls) -> "PlanningState":
        return cls(
            goal="",
            goal_type="",
            subgoals=[],
            active_subgoal_index=0,
            status="empty",
            created_tick=0,
            last_plan_tick=0,
            last_progress_tick=0,
            confidence=0.0,
            horizon="short",
        )

    def needs_replan(self, tick: int, plan_refresh_interval: int) -> bool:
        if self.status in {"empty", "blocked", "completed", "abandoned", "stale"}:
            return True
        return (tick - self.last_plan_tick) >= plan_refresh_interval
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_planning_state.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_planning_state.py simulation/planning_state.py simulation/config.py simulation/schemas.py
git commit -m "feat: add planning state and planner schemas"
```

### Task 2: Add Task Memory And Deterministic Retrieval

**Files:**
- Create: `simulation/retrieval.py`
- Modify: `simulation/memory.py`
- Test: `tests/test_memory.py`
- Test: `tests/test_retrieval.py`

**Step 1: Write the failing tests**

```python
from simulation.memory import Memory
from simulation.retrieval import RetrievalContext, rank_memory_entries


def test_task_memory_cap():
    mem = Memory()
    for i in range(20):
        mem.add_task_entry(tick=i, kind="plan_result", summary=f"entry {i}")
    assert len(mem.task) == 12
    assert mem.task[0].summary == "entry 8"


def test_retrieval_prioritizes_hunger_knowledge():
    context = RetrievalContext(
        hunger=85,
        energy=60,
        life=90,
        visible_resources={"fruit"},
        inventory_items=set(),
        current_goal="stabilize food",
        current_subgoal="move toward fruit",
        blockers=(),
    )
    ranked = rank_memory_entries(
        semantic=["Fruit reduces hunger quickly", "Rest helps when energy is low"],
        episodic=["I failed to reach the river yesterday"],
        task=["Plan blocked when fruit disappeared"],
        context=context,
        limit=2,
    )
    assert ranked[0] == "Fruit reduces hunger quickly"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory.py tests/test_retrieval.py -v`

Expected: FAIL because `add_task_entry`, `task`, `RetrievalContext`, and `rank_memory_entries` do not exist yet.

**Step 3: Write minimal implementation**

```python
# simulation/memory.py
from dataclasses import dataclass

from simulation.config import TASK_MEMORY_MAX


@dataclass
class TaskMemoryEntry:
    tick: int
    kind: str
    summary: str
    goal: str = ""
    outcome: str = ""


class Memory:
    def __init__(self):
        self.episodic: list[str] = []
        self.semantic: list[str] = []
        self.task: list[TaskMemoryEntry] = []
        self._last_compression_tick = 0

    def add_task_entry(self, tick: int, kind: str, summary: str, goal: str = "", outcome: str = ""):
        self.task.append(TaskMemoryEntry(tick=tick, kind=kind, summary=summary, goal=goal, outcome=outcome))
        if len(self.task) > TASK_MEMORY_MAX:
            self.task = self.task[-TASK_MEMORY_MAX:]


# simulation/retrieval.py
from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalContext:
    hunger: int
    energy: int
    life: int
    visible_resources: set[str]
    inventory_items: set[str]
    current_goal: str
    current_subgoal: str
    blockers: tuple[str, ...]


def _score_entry(entry: str, context: RetrievalContext) -> int:
    text = entry.lower()
    score = 0
    if context.hunger >= 80 and "hunger" in text:
        score += 5
    if any(resource in text for resource in context.visible_resources):
        score += 4
    if context.current_goal and any(word in text for word in context.current_goal.lower().split()):
        score += 3
    if any(blocker.lower() in text for blocker in context.blockers):
        score += 2
    return score


def rank_memory_entries(
    semantic: list[str],
    episodic: list[str],
    task: list[str],
    context: RetrievalContext,
    limit: int,
) -> list[str]:
    combined = semantic + episodic + task
    ranked = sorted(combined, key=lambda entry: _score_entry(entry, context), reverse=True)
    return ranked[:limit]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory.py tests/test_retrieval.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_memory.py tests/test_retrieval.py simulation/memory.py simulation/retrieval.py
git commit -m "feat: add task memory and deterministic retrieval"
```

### Task 3: Add Planner Prompts And Planner Module

**Files:**
- Create: `simulation/planner.py`
- Create: `prompts/agent/planner_system.txt`
- Create: `prompts/agent/planner.txt`
- Test: `tests/test_planner.py`

**Step 1: Write the failing tests**

```python
from unittest.mock import MagicMock

from simulation.planner import Planner
from simulation.planning_state import PlanningState


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

    planner = Planner(llm=llm)
    state = planner.plan(agent_name="Ada", tick=5, observation_text="fruit east", planner_context=["fruit helps"])

    assert isinstance(state, PlanningState)
    assert state.goal == "stabilize food"


def test_planner_returns_none_on_invalid_llm():
    llm = MagicMock()
    llm.generate_structured.return_value = None
    planner = Planner(llm=llm)
    assert planner.plan(agent_name="Ada", tick=5, observation_text="fruit east", planner_context=[]) is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_planner.py -v`

Expected: FAIL with `ModuleNotFoundError` for `simulation.planner`.

**Step 3: Write minimal implementation**

```python
# simulation/planner.py
from simulation import prompt_loader
from simulation.planning_state import PlanningState, PlanningSubgoal
from simulation.schemas import AgentPlanResponse


class Planner:
    def __init__(self, llm):
        self.llm = llm

    def plan(self, agent_name: str, tick: int, observation_text: str, planner_context: list[str], current_plan: PlanningState | None = None) -> PlanningState | None:
        if not self.llm:
            return None

        system_prompt = prompt_loader.render("agent/planner_system", agent_name=agent_name)
        user_prompt = prompt_loader.render(
            "agent/planner",
            tick=tick,
            observation_text=observation_text,
            planner_context="\n".join(f"- {entry}" for entry in planner_context) or "- none",
            current_plan=(current_plan.goal if current_plan else "none"),
        )
        typed = self.llm.generate_structured(user_prompt, AgentPlanResponse, system_prompt=system_prompt, temperature=0.3)
        if typed is None:
            return None

        return PlanningState(
            goal=typed.goal,
            goal_type=typed.goal_type,
            subgoals=[
                PlanningSubgoal(
                    description=s.description,
                    kind=s.kind,
                    target=s.target,
                    preconditions=list(s.preconditions),
                    completion_signal=s.completion_signal,
                    failure_signal=s.failure_signal,
                    priority=s.priority,
                )
                for s in typed.subgoals
            ],
            active_subgoal_index=0,
            status="active",
            created_tick=tick,
            last_plan_tick=tick,
            last_progress_tick=tick,
            confidence=typed.confidence,
            horizon=typed.horizon,
            success_signals=list(typed.success_signals),
            abort_conditions=list(typed.abort_conditions),
            blockers=[],
            rationale_summary=typed.rationale_summary,
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_planner.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_planner.py simulation/planner.py prompts/agent/planner_system.txt prompts/agent/planner.txt
git commit -m "feat: add planner prompts and planning module"
```

### Task 4: Wire Planning Into Agent Decisions

**Files:**
- Modify: `simulation/agent.py`
- Modify: `prompts/agent/decision.txt`
- Test: `tests/test_agent_prompts.py`
- Test: `tests/test_agent_planning.py`

**Step 1: Write the failing tests**

```python
from unittest.mock import MagicMock

from simulation.agent import Agent
from simulation.planning_state import PlanningState, PlanningSubgoal


def test_executor_prompt_includes_active_subgoal():
    agent = Agent(name="Ada", x=5, y=5)
    agent.planning_state = PlanningState(
        goal="stabilize food",
        goal_type="survival",
        subgoals=[PlanningSubgoal(description="move toward fruit", kind="move")],
        active_subgoal_index=0,
        status="active",
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
    prompt = agent._build_decision_prompt([{"x": 5, "y": 5, "tile": "land", "distance": 0}], tick=2)
    assert "ACTIVE SUBGOAL" in prompt
    assert "move toward fruit" in prompt


def test_agent_keeps_existing_plan_when_progressing(monkeypatch):
    agent = Agent(name="Ada", x=5, y=5, llm=MagicMock())
    agent.planning_state = PlanningState(
        goal="stabilize food",
        goal_type="survival",
        subgoals=[PlanningSubgoal(description="move toward fruit", kind="move")],
        active_subgoal_index=0,
        status="active",
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_prompts.py tests/test_agent_planning.py -v`

Expected: FAIL because `Agent` does not yet expose `planning_state`, planning-aware prompts, or `_planning_trace`.

**Step 3: Write minimal implementation**

```python
# simulation/agent.py
from simulation.config import ENABLE_EXPLICIT_PLANNING, PLAN_REFRESH_INTERVAL
from simulation.planner import Planner
from simulation.planning_state import PlanningState
from simulation.retrieval import RetrievalContext, rank_memory_entries


class Agent:
    def __init__(...):
        ...
        self.planning_state = PlanningState.empty()
        self.last_execution_result: dict = {}
        self.planner = Planner(llm) if llm else None

    def _should_replan(self, tick: int) -> bool:
        return self.planning_state.needs_replan(tick, PLAN_REFRESH_INTERVAL)

    def _planning_context(self) -> list[str]:
        context = RetrievalContext(
            hunger=self.hunger,
            energy=self.energy,
            life=self.life,
            visible_resources=set(),
            inventory_items=set(self.inventory.items.keys()),
            current_goal=self.planning_state.goal,
            current_subgoal=self.current_subgoal_text(),
            blockers=tuple(self.planning_state.blockers),
        )
        return rank_memory_entries(
            semantic=self.memory_system.semantic,
            episodic=self.memory_system.episodic,
            task=[entry.summary for entry in self.memory_system.task],
            context=context,
            limit=PLANNER_CONTEXT_MAX,
        )

    def decide_action(...):
        planning_trace = {}
        if ENABLE_EXPLICIT_PLANNING and self.planner and self._should_replan(tick):
            new_plan = self.planner.plan(...)
            if new_plan is not None:
                self.planning_state = new_plan
                planning_trace["plan_created"] = {"goal": new_plan.goal, "subgoal_count": len(new_plan.subgoals)}
        ...
        result = typed.model_dump() if typed is not None else self._fallback_decision(nearby_tiles)
        result["_planning_trace"] = planning_trace
        return result
```

Update `prompts/agent/decision.txt` to add:

```text
CURRENT GOAL:
$current_goal

ACTIVE SUBGOAL:
$active_subgoal

PLAN STATUS:
$plan_status
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_prompts.py tests/test_agent_planning.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_agent_prompts.py tests/test_agent_planning.py simulation/agent.py prompts/agent/decision.txt
git commit -m "feat: add planner executor loop to agents"
```

### Task 5: Emit Planning Events From Engine And Event Emitter

**Files:**
- Modify: `simulation/event_emitter.py`
- Modify: `simulation/engine.py`
- Test: `tests/test_event_emitter.py`
- Test: `tests/test_engine_planning_events.py`

**Step 1: Write the failing tests**

```python
def test_emit_plan_created(tmp_path, monkeypatch):
    em = _make_emitter(tmp_path, monkeypatch)
    em.emit_plan_created(3, "Ada", {"goal": "stabilize food", "subgoal_count": 2})
    em.close()
    ev = _read_events(tmp_path)[0]
    assert ev["event_type"] == "plan_created"
    assert ev["payload"]["goal"] == "stabilize food"


def test_engine_emits_subgoal_completed(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    planning_trace = {"subgoal_completed": {"description": "move toward fruit"}}
    action = {"action": "move", "direction": "east", "_planning_trace": planning_trace}
    with patch.object(engine.agents[0], "decide_action", return_value=action):
        engine.run()
    events = _read_events(engine.event_emitter.run_dir)
    assert "subgoal_completed" in [event["event_type"] for event in events]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_event_emitter.py tests/test_engine_planning_events.py -v`

Expected: FAIL because the new emitters and engine hooks do not exist yet.

**Step 3: Write minimal implementation**

```python
# simulation/event_emitter.py
def emit_plan_created(self, tick: int, agent_name: str, plan: dict):
    self._emit("plan_created", tick, plan, agent_id=agent_name)


def emit_plan_updated(self, tick: int, agent_name: str, plan: dict):
    self._emit("plan_updated", tick, plan, agent_id=agent_name)


def emit_plan_abandoned(self, tick: int, agent_name: str, payload: dict):
    self._emit("plan_abandoned", tick, payload, agent_id=agent_name)


def emit_subgoal_completed(self, tick: int, agent_name: str, payload: dict):
    self._emit("subgoal_completed", tick, payload, agent_id=agent_name)


def emit_subgoal_failed(self, tick: int, agent_name: str, payload: dict):
    self._emit("subgoal_failed", tick, payload, agent_id=agent_name)


# simulation/engine.py
planning_trace = action.pop("_planning_trace", None) or {}
if "plan_created" in planning_trace:
    self.event_emitter.emit_plan_created(tick, agent.name, planning_trace["plan_created"])
if "plan_updated" in planning_trace:
    self.event_emitter.emit_plan_updated(tick, agent.name, planning_trace["plan_updated"])
if "plan_abandoned" in planning_trace:
    self.event_emitter.emit_plan_abandoned(tick, agent.name, planning_trace["plan_abandoned"])
if "subgoal_completed" in planning_trace:
    self.event_emitter.emit_subgoal_completed(tick, agent.name, planning_trace["subgoal_completed"])
if "subgoal_failed" in planning_trace:
    self.event_emitter.emit_subgoal_failed(tick, agent.name, planning_trace["subgoal_failed"])
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_event_emitter.py tests/test_engine_planning_events.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_event_emitter.py tests/test_engine_planning_events.py simulation/event_emitter.py simulation/engine.py
git commit -m "feat: emit planning lifecycle events"
```

### Task 6: Update EBS Planning Metrics

**Files:**
- Modify: `simulation/ebs_builder.py`
- Modify: `tests/test_ebs_builder.py`

**Step 1: Write the failing tests**

```python
def test_self_generated_subgoals_uses_planning_events(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    events = [
        _decision(1, action="move"),
        {"run_id": "test", "tick": 1, "event_type": "plan_created", "agent_id": "Ada", "payload": {"goal": "stabilize food", "subgoal_count": 2}},
        {"run_id": "test", "tick": 2, "event_type": "subgoal_completed", "agent_id": "Ada", "payload": {"description": "move toward fruit"}},
        {"run_id": "test", "tick": 3, "event_type": "subgoal_completed", "agent_id": "Ada", "payload": {"description": "eat fruit"}},
    ]
    _write_events(run_dir, events)
    data = EBSBuilder(run_dir).build()
    assert data["components"]["autonomy"]["sub_scores"]["self_generated_subgoals"] > 0.0


def test_runs_without_planning_events_still_score_zero(tmp_path):
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ebs_builder.py -k subgoal -v`

Expected: FAIL because `self_generated_subgoals` is still hard-coded to `0.0`.

**Step 3: Write minimal implementation**

```python
# simulation/ebs_builder.py
plans_created = 0
subgoals_completed = 0
subgoals_failed = 0

for event in events:
    et = event.get("event_type")
    if et == "plan_created":
        plans_created += 1
    elif et == "subgoal_completed":
        subgoals_completed += 1
    elif et == "subgoal_failed":
        subgoals_failed += 1

planning_signal = subgoals_completed + subgoals_failed
self_generated_subgoals = min(1.0, planning_signal / max(1, decisions_total))

...
"autonomy": {
    "score": round(autonomy_score, 2),
    "weight": _WEIGHTS["autonomy"],
    "sub_scores": {
        "proactive_resource_acquisition": round(proactive_rate, 4),
        "environment_contingent_innovation": round(env_contingent_rate, 4),
        "self_generated_subgoals": round(self_generated_subgoals, 4),
    },
},
"planning": {
    "plans_created": plans_created,
    "subgoals_completed": subgoals_completed,
    "subgoals_failed": subgoals_failed,
},
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ebs_builder.py -k subgoal -v`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_ebs_builder.py simulation/ebs_builder.py
git commit -m "feat: measure planning signals in ebs"
```

### Task 7: Update Cornerstone Docs And Run Full Verification

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/01-architecture/architecture_context.md`
- Modify: `project-cornerstone/03-agents/agents_context.md`
- Modify: `project-cornerstone/13-future-work/future-work_context.md`

**Step 1: Update the architecture and decision docs**

Add a new decision entry describing:

- explicit `PlanningState`
- planner/executor split
- deterministic relevance retrieval
- planning event emission

Update the architecture and agent context docs so they mention:

- the new cognition loop
- planner cadence and replanning triggers
- task memory and retrieval changes
- planning events in the canonical event stream

Move the future-work note about explicit goal stacks from planned to implemented.

**Step 2: Run the targeted new test files**

Run:

```bash
pytest tests/test_planning_state.py tests/test_retrieval.py tests/test_planner.py tests/test_agent_planning.py tests/test_engine_planning_events.py -v
```

Expected: PASS

**Step 3: Run the broader regression suite**

Run: `pytest -m "not slow"`

Expected: PASS

**Step 4: Run a no-LLM smoke simulation**

Run: `uv run main.py --no-llm --ticks 5 --agents 1`

Expected: process exits `0`; the simulation runs without planner crashes or dead-agent regressions.

**Step 5: Commit docs and verification-safe changes**

```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/01-architecture/architecture_context.md project-cornerstone/03-agents/agents_context.md project-cornerstone/13-future-work/future-work_context.md
git commit -m "docs: record explicit planning architecture"
```

## Notes For The Implementer

- Keep planner failures non-fatal at all times. If planner JSON parsing fails, keep the previous valid plan or fall back to the current reactive path.
- Do not add embeddings, vector stores, or semantic search in this pass.
- Keep plan/event payloads small; `events.jsonl` is the canonical metrics source.
- Make `Agent.decide_action()` return planning metadata through hidden fields like `_planning_trace`, mirroring the existing `_llm_trace` pattern.
- Re-run `pytest -m "not slow"` before every final success claim.

## Execution Handoff

Plan saved to `docs/plans/2026-03-12-agent-long-term-planning.md`.

Two execution options:

**1. Subagent-Driven (this session)** - Use `superpowers:subagent-driven-development`, dispatch one fresh subagent per task, review between tasks, and keep changes isolated.

**2. Parallel Session (separate)** - Open a new session in a clean worktree and use `superpowers:executing-plans` to implement this document task-by-task.
