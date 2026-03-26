# 01A — Canonical `events.jsonl` Schema

_Status: code-aligned with `simulation/event_emitter.py` and `simulation/engine.py` as of 2026-03-26._

## Scope

`data/runs/<run_id>/events.jsonl` is the authoritative append-only event stream for a single run.

- `meta.json` is separate and holds run-wide metadata such as prompt hashes, git commit, model ids, `precedents_file`, and the normalized `experiment_profile`.
- WebSocket messages (`init`, `tick`, `control`) are a separate UI transport and are not the canonical analytics schema.

## Shared Envelope

Every line in `events.jsonl` is one JSON object with this envelope:

| Field | Type | Notes |
|---|---|---|
| `run_id` | `string` | Matches the run directory name under `data/runs/`. |
| `seed` | `integer \| null` | World seed used for the run. |
| `tick` | `integer` | `0` is reserved for `run_start`; simulation ticks begin at `1`. |
| `sim_time` | `object \| null` | `null` at tick `0`; otherwise `{"day": int, "hour": int}` from `DayCycle`. |
| `event_type` | `string` | One of the event types documented below. |
| `agent_id` | `string \| null` | Agent name for agent-scoped events; `null` for run-scoped events. |
| `payload` | `object` | Event-specific data. |

## Event Types

### `run_start`

Emitted once, first event in the file.

`agent_id = null`

| Payload field | Type | Notes |
|---|---|---|
| `config.width` | `integer` | World width. |
| `config.height` | `integer` | World height. |
| `config.max_ticks` | `integer \| null` | `null` means unbounded / `infinite`. |
| `config.agent_count` | `integer` | Initial agent count. |
| `config.agent_names` | `string[]` | Initial agent roster. |
| `config.agent_profiles` | `object[]` | Optional; currently included by the engine. Each entry contains `name` and `personality`. |
| `config.experiment_profile` | `object` | Optional; the normalized per-run profile serialized by the engine. Mirrors `meta.json.experiment_profile`. |
| `model_id` | `string` | Agent model id, or `"none"` when running without LLM. |
| `world_seed` | `integer \| null` | Seed used for world generation. |

### `agent_perception`

Pre-decision snapshot used by autonomy/EBS analysis.

| Payload field | Type | Notes |
|---|---|---|
| `pos` | `{"x": int, "y": int}` | Agent position before action selection. |
| `hunger` | `number` | Current hunger. |
| `energy` | `number` | Current energy. |
| `life` | `number` | Current life. |
| `resources_nearby` | `object[]` | Zero or more entries of `{"type": string, "tile": string, "dx": int, "dy": int}`. |

### `agent_decision`

Emitted after `Agent.decide_action()`.

| Payload field | Type | Notes |
|---|---|---|
| `parsed_action` | `object` | Structured action dict after removing hidden trace fields. |
| `parse_ok` | `boolean` | `true` for an LLM-produced structured response; `false` when fallback logic was used. |
| `action_origin` | `"base" \| "innovation"` | Derived from the action name against `BASE_ACTIONS`. |
| `prompt_ref` | `string` | Optional blob path, present when an LLM trace was captured. |
| `prompt_sha256` | `string` | Optional SHA-256 of the rendered prompt blob. |
| `raw_response_ref` | `string` | Optional blob path for the raw LLM response. |
| `response_sha256` | `string` | Optional SHA-256 of the raw response blob. |

### `oracle_resolution`

Emitted after `Oracle.resolve_action()`.

| Payload field | Type | Notes |
|---|---|---|
| `success` | `boolean` | Final oracle success/failure. |
| `effects.hunger` | `integer` | Normalized to `0` when absent. |
| `effects.energy` | `integer` | Normalized to `0` when absent. |
| `effects.life` | `integer` | Normalized to `0` when absent. |
| `cache_hit` | `boolean` | Whether the oracle reused cached precedent/output rather than creating a new LLM-backed result. |
| `prompt_ref` | `string \| null` | Prompt blob path when oracle LLM trace exists; otherwise `null`. |
| `prompt_sha256` | `string \| null` | SHA-256 of prompt blob; otherwise `null`. |
| `raw_response_ref` | `string \| null` | Raw response blob path when oracle LLM trace exists; otherwise `null`. |
| `response_sha256` | `string \| null` | SHA-256 of raw response blob; otherwise `null`. |

Current limitation:
- This payload does **not** currently include the action name, precedent key, message text/code, resource identifiers, or oracle context string. Consumers that need those details must correlate with neighboring events or the emitter must be extended first.

### `innovation_attempt`

Emitted before the oracle validates an `innovate` action, and also reused for item-derived innovations.

| Payload field | Type | Notes |
|---|---|---|
| `name` | `string` | Proposed action name. |
| `description` | `string` | Human-readable action description. |
| `requires` | `object \| null` | Nullable innovation prerequisites. |
| `produces` | `object \| null` | Nullable crafting outputs. |

### `innovation_validated`

Emitted after oracle approval/rejection of an innovation.

| Payload field | Type | Notes |
|---|---|---|
| `name` | `string` | Innovation name. |
| `approved` | `boolean` | Mirrors oracle success for the validation step. |
| `category` | `string \| null` | Oracle-assigned category when available. |
| `reason_code` | `string` | Compact validation outcome code. |
| `requires` | `object \| null` | Echoed innovation prerequisites. |
| `produces` | `object \| null` | Echoed crafting outputs. |
| `description` | `string \| null` | Description of the innovation. |
| `origin_item` | `string \| null` | Populated for item-derived innovations. |
| `discovery_mode` | `string \| null` | `"auto"` or `"manual"` for item-derived innovations. |
| `trigger_action` | `string \| null` | Action that triggered item-derived discovery. |

### `custom_action_executed`

Emitted when an already-approved innovation is executed.

| Payload field | Type | Notes |
|---|---|---|
| `name` | `string` | Custom action name. |
| `success` | `boolean` | Oracle success/failure for the execution. |
| `effects.hunger` | `integer` | Normalized to `0` when absent. |
| `effects.energy` | `integer` | Normalized to `0` when absent. |
| `effects.life` | `integer` | Normalized to `0` when absent. |

### `plan_created`
### `plan_updated`

Planning lifecycle events emitted when replanning succeeds.

| Payload field | Type | Notes |
|---|---|---|
| `goal` | `string` | Planner goal text. |
| `goal_type` | `string` | Planner goal type. |
| `subgoal_count` | `integer` | Number of subgoals in the active plan. |
| `confidence` | `number` | Rounded planner confidence. |

### `plan_abandoned`

Reserved by the event layer, but currently not emitted by the engine.

### `subgoal_completed`
### `subgoal_failed`

Emitted when subgoal evaluation marks a subgoal complete or failed.

| Payload field | Type | Notes |
|---|---|---|
| `subgoal` | `string` | Subgoal description. |
| `kind` | `string` | Subgoal kind/category. |

### `agent_state`

Post-action, post-passive-effects state snapshot.

| Payload field | Type | Notes |
|---|---|---|
| `life` | `number` | Final life after the tick's passive effects. |
| `hunger` | `number` | Final hunger after the tick's passive effects. |
| `energy` | `number` | Final energy after the tick's passive effects. |
| `pos` | `[int, int]` | Final position. |
| `alive` | `boolean` | Final alive/dead state. |
| `inventory` | `object` | Inventory item map. |
| `memory_semantic` | `integer` | Current semantic memory count. |

### `memory_compression_result`

Emitted after semantic-memory compression runs.

| Payload field | Type | Notes |
|---|---|---|
| `episode_count` | `integer` | Episodic entries available to compression. |
| `learnings` | `string[]` | Accepted semantic learnings returned by compression. |

### `agent_birth`

Emitted when a child agent is spawned.

| Payload field | Type | Notes |
|---|---|---|
| `child_name` | `string` | Child agent name. |
| `generation` | `integer` | Child generation. |
| `born_tick` | `integer` | Tick at which the child was born. |
| `parent_ids` | `string[]` | Parent agent names. |
| `pos` | `[int, int]` | Spawn position. |
| `personality` | `object` | Full personality trait snapshot. |

### `run_end`

Emitted once, last event before the file handle closes.

`agent_id = null`

| Payload field | Type | Notes |
|---|---|---|
| `survivors` | `string[]` | Names of agents still alive at the end of the run. |
| `total_ticks` | `integer` | Final tick count reached by the run. |

## Current Emission Order

The stream is append-only and ordered exactly as emitted by the engine. The high-level order is:

1. `run_start`
2. For each tick and each acting agent:
   - `agent_perception`
   - `agent_decision`
   - zero or more planning lifecycle events
   - `innovation_attempt` when relevant
   - `oracle_resolution`
   - `innovation_validated` and/or `custom_action_executed` when relevant
   - zero or more derived item-innovation events
   - zero or more subgoal outcome events
   - `agent_birth` when reproduction succeeds
   - `agent_state`
3. End-of-tick compression events: `memory_compression_result`
4. `run_end`

## Blob References

When prompt/raw-response refs are present, they are relative paths rooted at the run directory:

- `blobs/prompts/...`
- `blobs/llm_raw/...`

Blob writes are content-deduplicated by SHA-256. Identical content may be referenced by multiple events through the same relative path.

## Known Gaps

- The schema is not versioned inside `events.jsonl` yet.
- There are no dedicated world-resource events such as `resource_consumed` or `resource_regenerated`.
- `oracle_resolution` is intentionally compact and currently omits several fields some analytics plans once assumed would exist.
