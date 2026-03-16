# EBS Autonomy Component Rebuild Design

**Date:** 2026-03-16
**Status:** Approved

## Problem

The Autonomy component of the EBS was designed before long-term memory and explicit planning existed. Its three sub-scores (`proactive_resource_acquisition`, `environment_contingent_innovation`, `self_generated_subgoals`) only measure reactive/behavioral intelligence. Now that agents have:

- Semantic memory (episodic → semantic compression every 10 ticks)
- Task memory and deterministic retrieval (PR #45)
- Explicit planner/executor loop with structured subgoals (PR #45)

...two important capabilities are underrepresented: knowledge accumulation over time and goal-directed planning effectiveness.

## Decision

Rebuild the Autonomy component internals. Keep the weight at **13%** of total EBS. Replace the three existing sub-scores with three new ones that cover behavior, memory, and planning.

## Design

### Component Weight

Unchanged: `0.13` of total EBS.

### Sub-scores (weights sum to 1.0)

| Sub-score | Weight | What it measures |
|---|---|---|
| `behavioral_initiative` | 25% | Proactive and environment-responsive behavior |
| `knowledge_accumulation` | 37.5% | Whether agents build and retain semantic knowledge |
| `planning_effectiveness` | 37.5% | Whether agents form and complete structured plans |

### Formula

```
autonomy_score = 100 × (
    0.25  × behavioral_initiative
  + 0.375 × knowledge_accumulation
  + 0.375 × planning_effectiveness
)
```

### Signal Definitions

#### behavioral_initiative
Consolidation of the two existing behavioral signals, equal weight:

```
behavioral_initiative = (proactive_rate + env_contingent_rate) / 2
```

- `proactive_rate` — unchanged from current implementation: moves toward a visible resource when hunger is non-urgent divided by total moves
- `env_contingent_rate` — unchanged: innovation attempts when hunger is above threshold divided by total attempts

#### knowledge_accumulation
Two signals from events, equal weight:

```
knowledge_accumulation = (semantic_growth + compression_yield) / 2
```

- `semantic_growth` — how full is each agent's long-term semantic memory at end of run?
  ```
  semantic_growth = mean over all agents of (last memory_semantic count / MEMORY_SEMANTIC_MAX)
  ```
  Source: last `agent_state` event per agent, field `memory_semantic`. **Note:** `emit_agent_state` in `simulation/event_emitter.py` does not currently include this field — it must be added as a one-line change to the emitter (see Touch Points). The field is already present on `Agent.get_status()`.

- `compression_yield` — how much knowledge does each memory compression pass produce relative to its input?
  ```
  compression_yield = mean over compression events of min(1.0, len(learnings) / episode_count)
  ```
  Source: `memory_compression_result` events, fields `learnings` and `episode_count`. Both fields are already emitted by `emit_memory_compression_result`. Events where `episode_count == 0` are skipped. Returns 0.0 if no compression events occurred. **Note:** the existing `learnings_log` accumulator in `ebs_builder.py` only stores `learnings` — it must be extended to also store `episode_count` per event.

#### planning_effectiveness
Quantity and quality of planning activity, equal weight:

```
planning_effectiveness = (plan_completion_rate + planning_activity) / 2
```

- `plan_completion_rate` — of started subgoals, how many completed successfully?
  ```
  plan_completion_rate = subgoals_completed / (subgoals_completed + subgoals_failed)
  ```
  Returns 0.0 when no subgoals exist (planning disabled or no plans created).

- `planning_activity` — what fraction of agent action time involves planning?
  ```
  planning_activity = min(1.0, (subgoals_completed + subgoals_failed) / action_total)
  ```
  This is the existing `self_generated_subgoals` signal, renamed for clarity.

### Output Shape in ebs.json

`detail` is a sibling of `sub_scores`, not nested inside it. This preserves the schema contract where every value under `sub_scores` is a float, consistent with all other EBS components.

```json
"autonomy": {
  "score": 42.15,
  "weight": 0.13,
  "sub_scores": {
    "behavioral_initiative": 0.4800,
    "knowledge_accumulation": 0.3200,
    "planning_effectiveness": 0.1500
  },
  "detail": {
    "proactive_rate": 0.6000,
    "env_contingent_rate": 0.3600,
    "semantic_growth": 0.4000,
    "compression_yield": 0.2400,
    "plan_completion_rate": 0.2000,
    "planning_activity": 0.1000
  }
}
```

`sub_scores` contains the three weighted sub-scores (all floats). `detail` exposes the six underlying signals for debugging and analysis.

### Edge Cases

| Condition | Behaviour |
|---|---|
| No moves recorded | `proactive_rate` = 0 |
| No innovation attempts | `env_contingent_rate` = 0 |
| No `agent_state` events | `semantic_growth` = 0 |
| No compression events | `compression_yield` = 0 |
| `episode_count` = 0 in a compression event | skip that event |
| No subgoals (planning disabled) | `plan_completion_rate` = `planning_activity` = 0 |

All zeros cascade gracefully. A run with planning disabled scores 0 on `planning_effectiveness` but is not broken.

## Instrumentation Change Required

One field must be added to an existing event emitter. No new event types are introduced.

- `agent_state` events must include `memory_semantic` (int) in their payload. The field is already computed on `Agent.get_status()` — it just needs forwarding into `emit_agent_state` in `simulation/event_emitter.py`.

All other signals are already fully present in `events.jsonl`:
- `memory_compression_result` (fields `learnings`, `episode_count`)
- `plan_created`, `subgoal_completed`, `subgoal_failed`
- `agent_decision`, `agent_perception`

## Touch Points

| File | Change |
|---|---|
| `simulation/event_emitter.py` | Add `memory_semantic` (int) to `emit_agent_state` payload |
| `simulation/ebs_builder.py` | (1) Extend `learnings_log` accumulator to also store `episode_count`; (2) add `memory_semantic` tracking from `agent_state` events; (3) replace autonomy scoring block; (4) update output dict structure |
| `project-cornerstone/00-master-plan/DECISION_LOG.md` | Add decision entry |
| `project-cornerstone/03-agents/agents_context.md` | Update EBS autonomy description |
| `tests/test_ebs_builder.py` | Update or add tests for new sub-scores and output shape |

## Out of Scope

- Changing any other EBS component (Novelty, Utility, Realization, Stability, Longevity)
- Changing the total Autonomy weight (stays at 13%)
- Adding new events to `events.jsonl`
- Changing the memory system or planning system
- Measuring inherited memory quality (children with `[Inherited]` learnings vs without) — future work
