# Drop Item Action Design

- **Date:** 2026-03-12
- **Status:** Approved
- **Audience:** Emerge maintainers working on inventory, oracle action resolution, metrics, and cornerstone docs
- **Primary goal:** Add a basic built-in action that lets agents drop inventory items onto the world
- **Focus:** Keep the feature compatible with the current one-resource-stack-per-tile world model

## 1. Problem Statement

Agents can currently:

- pick up world resources into inventory
- eat from inventory
- give inventory items to adjacent agents

They cannot intentionally remove inventory items into the world.

That creates two practical gaps:

1. inventory management is one-way unless another agent is present
2. agents cannot deliberately place resources back into the environment for later pickup or transfer

The current world model only supports one resource stack per tile, so any drop mechanic must respect that constraint instead of widening the resource system.

## 2. Design Goals

The feature should:

1. add a new built-in action with clear prompt semantics
2. let agents place dropped items on their current tile
3. preserve the existing world resource model
4. keep metrics changes minimal and leverage existing action counting
5. stay deterministic and fully oracle-controlled

The feature should not:

- redesign the world to support multiple resource stacks per tile
- overload a social action such as `give_item`
- expand the metrics schema beyond what is needed for action visibility

## 3. Approaches Considered

### Option A: Add `drop_item` as a new built-in action

Agents use a dedicated action:

```json
{"action": "drop_item", "item": "<item_name>", "quantity": 1, "reason": "..."}
```

**Pros**

- explicit and easy for the model to use
- consistent with `give_item`
- no world-model expansion required
- naturally appears in existing `actions.by_type` metrics

**Cons**

- adds one more built-in action to prompts and oracle dispatch

### Option B: Reframe dropping as a generic placement action

Use a more abstract action such as `place_item`.

**Pros**

- conceptually flexible

**Cons**

- introduces new terminology that is less natural than "drop"
- does not buy meaningful capability over a simpler name

### Option C: Reuse `give_item` with a synthetic ground target

Example: `{"action":"give_item","target":"ground",...}`

**Pros**

- avoids adding a new action name

**Cons**

- mixes world interaction with social semantics
- makes prompts and metrics less clear
- complicates oracle validation

## 4. Chosen Direction

Adopt **Option A** and add a new built-in action named `drop_item`.

This is the narrowest change that matches current system boundaries:

- agents express an explicit intent to drop inventory
- the oracle remains the sole authority over inventory and world mutation
- the world remains limited to one resource stack per tile

## 5. Action Contract

### Action shape

```json
{"action": "drop_item", "item": "<item_name>", "quantity": 1, "reason": "..."}
```

### Resolution rules

- `item` must be present and non-blank
- `quantity` defaults to `1` when missing or invalid, matching `give_item`
- non-positive quantity fails
- the agent must carry at least the requested quantity
- the action uses the agent's current tile only

### Tile interaction rules

- if the tile has no resource, create a new resource stack with the dropped item
- if the tile already has the same resource type, increase that stack's quantity
- if the tile has a different resource type, fail

### Energy rule

`drop_item` should cost `0` energy, matching `pickup`

Rationale:

- this is an inventory placement action, not a strenuous world action
- it preserves a simple mental model: moving items in and out of inventory is free unless social transfer is involved

## 6. Architecture and Component Changes

### `simulation/config.py`

- add `drop_item` to `INITIAL_ACTIONS`
- add `ENERGY_COST_DROP = 0` so action costs remain explicit in configuration

### `simulation/agent.py`

- include `drop_item` in `has_energy_for()`
- expose the action automatically through the existing prompt assembly via `self.actions`

### `simulation/oracle.py`

- add a dispatch branch in `resolve_action()`
- implement `_resolve_drop_item(agent, action, tick)`
- perform validation before mutation
- update world state and inventory in one deterministic path
- write success and failure memories consistent with existing base actions

### `simulation/world.py`

Add a helper such as:

```python
place_resource(x: int, y: int, item: str, quantity: int) -> bool
```

Behavior:

- returns `False` without mutation if the tile contains a different resource type
- creates a resource stack on empty tile
- increments the quantity for a same-type stack

This keeps direct resource mutations encapsulated in the world layer instead of open-coding `world.resources[...]` updates in the oracle.

## 7. Metrics and Observability

No new event type is required for the first iteration.

Current instrumentation already counts parsed actions from `agent_decision` events into:

```json
summary["actions"]["by_type"]
```

Once `drop_item` becomes a built-in action, it will automatically appear in:

- run-level action totals
- per-type action counts

Planned metrics work:

- add regression coverage proving `drop_item` is counted in `actions.by_type`
- update metrics-facing documentation so the action taxonomy remains accurate

This deliberately avoids expanding the metrics schema with bespoke inventory-drop counters before there is a demonstrated need.

## 8. Error Handling and Invariants

Failure cases:

- missing or blank `item`
- non-positive `quantity`
- insufficient inventory
- tile occupied by a different resource type

In all failure cases:

- the agent inventory must remain unchanged
- the tile resource must remain unchanged
- the oracle returns `success=False`
- the agent receives a useful episodic memory

The feature preserves core invariants:

- oracle remains the single mutation gateway
- stats remain clamped
- dead agents still never act
- equivalent inputs produce equivalent outcomes

## 9. Testing Plan

Create focused oracle tests in `tests/test_drop_item.py`, modeled after `tests/test_give_item.py`.

### Required cases

- success on empty tile creates a resource stack
- success on same-type tile merges quantity
- failure on conflicting tile resource type
- failure when the agent lacks the requested item
- failure on non-positive quantity
- invalid quantity defaults to `1`
- failure leaves inventory and tile unchanged
- success records episodic memory

### Additional regression coverage

- `tests/test_metrics_builder.py`: verify `drop_item` appears in `summary["actions"]["by_type"]`
- prompt-related test coverage: verify the system prompt documents the new action

## 10. Documentation Updates

Update these cornerstone files during implementation:

- `project-cornerstone/03-agents/agents_context.md`
- `project-cornerstone/04-oracle/oracle_context.md`
- `project-cornerstone/01-architecture/architecture_context.md`
- `project-cornerstone/00-master-plan/MASTER_PLAN.md`
- `project-cornerstone/00-master-plan/DECISION_LOG.md`

The decision log entry should record:

- dropped items create or merge a same-type resource stack on the current tile
- drops fail when the tile already holds a different resource type
- the world model remains one resource stack per tile

## 11. Touch Points

- `simulation/config.py`
- `simulation/agent.py`
- `simulation/oracle.py`
- `simulation/world.py`
- `simulation/schemas.py`
- `prompts/agent/system.txt`
- `tests/test_drop_item.py`
- `tests/test_metrics_builder.py`
- cornerstone docs listed above
