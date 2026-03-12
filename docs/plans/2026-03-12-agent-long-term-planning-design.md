# Agent Long-Term Planning Design

- **Date:** 2026-03-12
- **Status:** Approved
- **Audience:** Emerge maintainers working on agent cognition, memory retrieval, and planning behavior
- **Primary goal:** Improve long-horizon agent behavior by turning retained knowledge into durable, multi-tick action plans
- **Focus:** Agents currently remember useful lessons but still behave reactively at action-selection time

## 1. Problem Statement

The current agent cognition loop is memory-aware but still reactive.

The repository already has:

- dual memory in [`simulation/memory.py`](../../simulation/memory.py): episodic events plus semantic learnings
- a rich per-tick decision prompt in [`simulation/agent.py`](../../simulation/agent.py) with stats, perception, relationships, family context, and memory
- canonical observability in [`simulation/event_emitter.py`](../../simulation/event_emitter.py)

What it does not have is durable planning state.

Today, agents receive a per-tick prompt and emit one action. There is no first-class notion of:

- current goal
- ordered subgoals
- progress toward a plan
- blockers
- plan freshness
- replanning triggers

As a result, agents can retain facts such as "fruit reduces hunger" while still failing to pursue a coherent multi-tick strategy such as "move toward fruit, pick it up, then eat before hunger becomes critical."

## 2. Current System Analysis

### Strengths

- **Dual memory exists already:** semantic memory preserves lessons across long runs instead of losing everything to recency.
- **Prompt context is rich:** the agent sees nearby resources, terrain, nearby agents, relationships, family context, and stats.
- **Fallbacks are disciplined:** invalid LLM outputs do not crash the loop.
- **Observability foundation exists:** prompts, raw responses, and memory-compression outputs already flow into `events.jsonl`.

### Weaknesses

- **Recency-biased retrieval:** `Memory.to_prompt()` sends the last N semantic and episodic entries, not the most relevant ones for the current objective.
- **No persistent plan state:** all cognition happens inside a single tick-local prompt.
- **No planner/executor split:** the same decision call must both invent strategy and pick the next primitive action.
- **No subgoal observability:** `simulation/ebs_builder.py` still hard-codes `self_generated_subgoals` to `0.0`.
- **No structured recovery path:** when a partial strategy fails, the agent has no explicit record of why the plan broke.

### Root Cause

The current architecture stores knowledge but does not operationalize it.

Memory is treated as prompt context, not as part of a durable control system. Long-term planning therefore depends on the LLM re-deriving the same strategy from scratch every tick, which is exactly the behavior that degrades under prompt noise and local urgency.

## 3. Design Goals

The redesign should:

1. preserve the current Oracle and world-mutation boundaries
2. improve multi-tick coherence without requiring a full world-model search system
3. keep planner failures non-fatal
4. reduce prompt noise by retrieving relevant evidence instead of dumping recency slices
5. produce measurable planning signals in the event stream and metrics

The redesign should not:

- move mutation logic into the agent
- require embeddings or a vector database in the first iteration
- require a planner call every tick
- replace the current memory system wholesale

## 4. Approaches Considered

### Option A: Prompt-Only Goal Injection

Add a textual "current goal" and "unfinished task" section to the existing decision prompt.

**Pros**

- low implementation cost
- minimal schema change

**Cons**

- fragile, because plan state remains unstructured prompt text
- hard to validate, expire, or measure
- does not fix retrieval quality

### Option B: Hybrid Planner/Executor With Explicit Plan State

Add a structured planner that runs periodically or on trigger conditions, and a lighter executor that acts each tick against the current subgoal.

**Pros**

- directly addresses the current failure mode
- keeps Oracle and world model intact
- enables measurable subgoal-level metrics
- allows deterministic retrieval without overengineering

**Cons**

- introduces new agent state, schemas, prompts, and events
- requires careful fallback behavior to avoid plan thrash

### Option C: Full Hierarchical Search-Based Cognition

Add explicit world beliefs, utility scoring, and multi-step lookahead or rollouts.

**Pros**

- highest long-term ceiling

**Cons**

- complexity is disproportionate to current architecture
- harder to keep deterministic and debuggable
- too much product risk for the first planning upgrade

### Chosen Direction

**Option B** is the recommended design.

It solves the central problem, fits the current system boundaries, and can be rolled out incrementally behind a feature flag.

## 5. Proposed Architecture

The agent cognition loop becomes:

1. `Observe`
2. `Retrieve`
3. `Plan`
4. `Execute`
5. `Reflect`
6. `Consolidate`

### What Stays The Same

- `simulation/oracle.py` remains the sole authority for outcomes and world mutation.
- `simulation/engine.py` still owns the tick loop.
- `simulation/memory.py` remains the source of episodic and semantic memory.
- Existing non-LLM fallbacks continue to guarantee safe execution.

### What Changes

- Agents gain explicit `PlanningState`.
- Memory retrieval becomes relevance-based instead of purely recency-based.
- Planning and execution become separate concerns.
- Planning signals become first-class events and metrics.

## 6. Planning State Model

Add a durable planning ledger attached to each agent.

### New State

`PlanningState` should include:

- `goal`: current high-level objective
- `goal_type`: survival, exploration, crafting, social, reproduction
- `subgoals`: ordered list of actionable intermediate steps
- `active_subgoal_index`: which step the executor is currently serving
- `status`: active, blocked, completed, abandoned, stale
- `created_tick`
- `last_plan_tick`
- `last_progress_tick`
- `confidence`
- `horizon`: short or medium
- `success_signals`
- `abort_conditions`
- `blockers`
- `rationale_summary`

### Subgoal Model

Each subgoal should be structured rather than free text:

- `description`
- `kind`: move, acquire, consume, rest, teach, craft, communicate, reproduce, innovate
- `target`
- `preconditions`
- `completion_signal`
- `failure_signal`
- `priority`

This makes subgoal progress inspectable, testable, and measurable.

## 7. Memory Model Changes

The design keeps dual memory and adds a third layer for active planning.

### 7.1 Episodic Memory

No fundamental behavioral change. It remains the short-term record of concrete events.

### 7.2 Semantic Memory

No fundamental structural change. It remains the store of compressed general learnings.

### 7.3 Task Memory

Add a bounded `task memory` store that tracks:

- plans that were created
- plans that succeeded or failed
- blockers that repeatedly occurred
- concise summaries of why past plans worked or broke

This is not a replacement for `PlanningState`. It is a historical ledger that supports better future planning.

## 8. Retrieval Design

Replace recency-only prompt assembly with deterministic relevance scoring.

### Inputs To Retrieval

- current stats and urgency band
- current tile and visible resources
- inventory
- visible agents and relationships
- incoming messages
- active goal and subgoal
- recent success and failure outcomes

### Scoring Principles

Memory items should score higher when they match:

- urgent needs such as hunger, low energy, or injury
- resources relevant to the active goal
- terrain and item requirements relevant to the subgoal
- repeated failures or blockers
- nearby social context when the plan is social

### Output

Build two prompt-ready slices:

- `planner_context`
- `executor_context`

The planner should see the small set of memories most relevant to goal formation and replanning.

The executor should see the even smaller set of evidence needed for the next action.

### Non-Goal

Do not introduce embeddings or semantic search in the first iteration. Deterministic scoring is sufficient and easier to debug.

## 9. Runtime Flow

Each tick for a living agent becomes:

1. Build an observation snapshot from stats, environment, inventory, social context, and current plan state.
2. Retrieve relevant memory for the active situation.
3. Decide whether replanning is required.
4. If replanning is required, call the planner and update `PlanningState`.
5. Call the executor to choose the next concrete action for the active subgoal.
6. Send the action to the Oracle for resolution.
7. Reflect on the outcome and update plan progress, blockers, and task memory.
8. Continue normal memory compression on its existing cadence.

This changes the agent question from:

> "What should I do right now?"

to:

> "Given my current plan, what is the next action that best advances the active subgoal?"

## 10. Replanning Policy

The planner should not run every tick.

### Trigger Conditions

Replan when any of the following is true:

- no active plan exists
- the current subgoal completed
- the current subgoal failed
- the plan became blocked
- critical survival thresholds were crossed
- required target or resource is no longer available
- the plan is stale: `tick - last_plan_tick >= PLAN_REFRESH_INTERVAL`

### Planner Cadence

Use a hybrid cadence:

- periodic refresh every few ticks
- immediate replanning on failure, completion, or significant state shift

This keeps long-term behavior durable without making the planner a per-tick bottleneck.

## 11. Planner/Executor Split

### Planner

The planner call should produce structured output:

- goal
- goal_type
- ordered subgoals
- success signals
- abort conditions
- confidence
- rationale summary

The planner prompt should receive:

- observation snapshot
- planner-specific retrieved memory
- current plan state if one exists
- the last execution outcome

### Executor

The executor remains the per-tick decision maker, but with a narrower job:

- act against the active subgoal
- prefer plan-consistent actions
- escalate blockers rather than inventing a fresh strategy each tick

The executor prompt should receive:

- observation snapshot
- active goal and current subgoal
- executor-specific retrieved memory
- recent execution result

## 12. Failure Handling

Planner failure must never stop the agent from acting.

### Rules

- if the planner call fails, keep the last valid plan if it is still usable
- if no usable plan exists, fall back to the existing reactive decision path
- if the executor repeatedly fails to progress, mark the subgoal blocked and trigger replanning
- if a plan becomes stale, do not blindly follow it; replan

### Bounds

- `PlanningState` must be bounded in size
- task memory must be bounded in size
- any planner schema parse failure must degrade safely

## 13. Observability And Metrics

Add explicit planning events to the canonical event stream:

- `plan_created`
- `plan_updated`
- `plan_abandoned`
- `subgoal_completed`
- `subgoal_failed`

### Why This Matters

The existing metrics stack already measures many cognition-adjacent signals, but it cannot yet measure real planning because the runtime does not expose planning events.

This redesign should unlock:

- real `self_generated_subgoals`
- plan completion rate
- replan frequency
- average plan horizon
- goal persistence across ticks
- blocker frequency
- correlation between plans and survival or innovation outcomes

## 14. Testing Strategy

The first implementation should be TDD-driven and focus on deterministic behaviors.

### Unit Tests

- relevance scoring selects the right memory items for survival-critical contexts
- replanning triggers fire only on intended conditions
- planner state transitions are correct
- stale or blocked plans are invalidated safely
- fallback behavior preserves action selection when planner output is invalid

### Integration Tests

- agent maintains the same plan across multiple ticks when progress is happening
- agent replans when a resource disappears or a blocker appears
- agent follows multi-step sequences more consistently than the current reactive baseline
- planning events appear in `events.jsonl` with valid schema

### Regression Focus

- dead agents never act
- stats remain clamped
- Oracle remains the sole mutation gateway
- non-LLM mode still works

## 15. Rollout Plan

Ship the redesign incrementally behind a feature flag.

### Phase 1

- add planner schemas
- add `PlanningState`
- add deterministic retrieval

### Phase 2

- add planner prompt and planner call
- preserve current executor behavior as fallback

### Phase 3

- narrow the executor prompt around active subgoals
- add planning reflection and task memory updates

### Phase 4

- emit planning events
- wire planning metrics into `simulation/ebs_builder.py`

### Phase 5

- tune planner cadence and retrieval weights using observed run data

## 16. Recommended File-Level Impact

Expected future implementation areas:

- `simulation/agent.py`
- `simulation/memory.py`
- `simulation/engine.py`
- `simulation/schemas.py`
- `simulation/event_emitter.py`
- `simulation/ebs_builder.py`
- `prompts/agent/decision.txt`
- new modules such as:
  - `simulation/planning_state.py`
  - `simulation/planner.py`
  - `simulation/retrieval.py`
- new tests covering planner state, retrieval, and event emission

## 17. Recommendation

The recommended path is a deep but staged redesign:

- keep Oracle and world mutation unchanged
- add explicit planner state to agents
- split cognition into planner and executor roles
- replace recency-only retrieval with deterministic relevance retrieval
- treat planning outcomes as first-class observable events

This is the smallest redesign that should materially improve long-horizon behavior without collapsing into a much larger search-based architecture.
