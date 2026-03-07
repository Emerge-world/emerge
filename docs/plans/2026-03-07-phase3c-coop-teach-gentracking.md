# Phase 3c: Cooperation + Teaching + Generational Tracking

## Context

Phase 3a (personality + perception) and 3b (communication + trust + conflict) are complete. Agents can perceive neighbors, communicate, and build trust relationships. Phase 3c adds the ability to **cooperate** by giving items, **teach** innovations, and lays groundwork for Phase 4 reproduction with generational tracking fields.

Design doc: `docs/plans/2026-03-06-phase3-social-design.md` (lines 230-300).

---

## Implementation: 3 PRs (one feature each)

### PR 1: `give_item` base action

**Files to modify:**

1. **`simulation/config.py`** — Add constants:
   ```python
   GIVE_ITEM_ENERGY_COST = 2
   GIVE_ITEM_TRUST_DELTA = 0.15
   ```
   Add `"give_item"` to `BASE_ACTIONS` (line 132).

2. **`simulation/oracle.py`** — Add `_resolve_give_item(self, agent, action, tick)`:
   - Wire into dispatcher (after line 142, before the `agent.actions` fallback)
   - Validations (follow `_resolve_communicate` pattern at line 490):
     - Target exists & alive (via `self.current_tick_agents`)
     - Adjacent: manhattan distance ≤ 1
     - Energy: `agent.energy >= GIVE_ITEM_ENERGY_COST`
     - Giver has item: `agent.inventory.has(item, quantity)`
     - Target has space: `target.inventory.free_space() >= quantity`
   - Effects:
     - `agent.inventory.remove(item, quantity)`
     - `target.inventory.add(item, quantity)`
     - `agent.energy -= GIVE_ITEM_ENERGY_COST`
     - Trust: `target.update_relationship(agent.name, GIVE_ITEM_TRUST_DELTA, tick, is_cooperation=True)`
     - Episodic memory for both agents
   - Import `GIVE_ITEM_ENERGY_COST, GIVE_ITEM_TRUST_DELTA` from config

3. **`simulation/agent.py`** — Add `"give_item": GIVE_ITEM_ENERGY_COST` to `has_energy_for()` dict (line 129). Import the constant.

4. **`prompts/agent/system.txt`** — Add after communicate line (line 18):
   ```
   - give_item: {"action": "give_item", "target": "<name>", "item": "<item_name>", "quantity": 1, "reason": "..."}
     (give an item from your inventory to an adjacent agent; costs 2 energy)
   ```

5. **`tests/test_give_item.py`** — New file, ~10 tests:
   - Happy path: item transferred, inventories updated
   - Energy cost applied
   - Trust +0.15 on target toward giver, cooperations incremented
   - Both agents get episodic memory
   - Failures: target not found, target dead, not adjacent, insufficient energy, giver lacks item, target inventory full

---

### PR 2: `teach` base action

**Files to modify:**

1. **`simulation/config.py`** — Add constants:
   ```python
   TEACH_ENERGY_COST_TEACHER = 8
   TEACH_ENERGY_COST_LEARNER = 5
   TEACH_TRUST_DELTA = 0.20
   ```
   Add `"teach"` to `BASE_ACTIONS`.

2. **`simulation/oracle.py`** — Add `_resolve_teach(self, agent, action, tick)`:
   - Wire into dispatcher after `give_item` branch
   - Validations:
     - Target exists & alive (via `self.current_tick_agents`)
     - Within vision radius: manhattan distance ≤ `AGENT_VISION_RADIUS` (same as communicate, NOT adjacency)
     - Teacher knows skill: `f"innovation:{skill}" in self.precedents`
     - Skill is NOT a base action: `skill not in BASE_ACTIONS`
     - Target does NOT already know it: `skill not in target.actions`
     - Teacher energy ≥ 8, learner energy ≥ 5
   - Effects:
     - `agent.energy -= TEACH_ENERGY_COST_TEACHER`
     - `target.energy -= TEACH_ENERGY_COST_LEARNER`
     - `target.actions.append(skill)` — learner gains the action
     - Trust: both agents get +0.20, `is_cooperation=True`
     - Episodic memory for both
   - **No LLM call** — deterministic precedent copy (DEC-024)
   - Import `TEACH_ENERGY_COST_TEACHER, TEACH_ENERGY_COST_LEARNER, TEACH_TRUST_DELTA` from config

3. **`simulation/agent.py`** — Add `"teach": TEACH_ENERGY_COST_TEACHER` to `has_energy_for()`. Import constant.

4. **`prompts/agent/system.txt`** — Add after give_item line:
   ```
   - teach: {"action": "teach", "target": "<name>", "skill": "<innovation_name>", "reason": "..."}
     (teach a visible agent one of your innovations; costs 8 energy for you, 5 for learner)
   ```

5. **`tests/test_teach.py`** — New file, ~13 tests:
   - Happy path: learner gains action
   - Energy cost: teacher -8, learner -5
   - Trust: both +0.20, cooperations incremented
   - Both get episodic memory
   - Target within vision radius succeeds
   - Failures: target not found, target dead, out of range, teacher doesn't know skill, target already knows, base action rejected, teacher insufficient energy, learner insufficient energy
   - No LLM call made (mock LLM, assert not called)

---

### PR 3: Generational tracking fields

**Files to modify:**

1. **`simulation/agent.py`** — Add fields to `__init__()`:
   ```python
   self.generation: int = 0
   self.parent_ids: list[str] = []
   self.born_tick: int = 0
   ```
   Include in `get_status()` output dict.

2. **`tests/test_generational.py`** — New file, 3 tests:
   - Default values: generation=0, parent_ids=[], born_tick=0
   - Fields appear in `get_status()`
   - Fields are settable (generation=1, parent_ids=["Ada", "Bruno"], born_tick=42)

---

## Decision Log Entries

After all PRs, add to `project-cornerstone/00-master-plan/DECISION_LOG.md`:

- **DEC-023**: `give_item` generalized from `share_food` — any inventory item, not just food
- **DEC-024**: Teaching as deterministic precedent copy — no LLM call, preconditions enforced by Oracle
- **DEC-025**: Generational tracking fields added in Phase 3 as Phase 4 groundwork

## Cornerstone Updates

- `project-cornerstone/00-master-plan/MASTER_PLAN.md` — Check Phase 3c items
- `project-cornerstone/03-agents/agents_context.md` — Document give_item, teach, generation fields
- `project-cornerstone/07-interaction/interaction_context.md` — Document cooperation mechanics

---

## Verification

```bash
# After each PR:
uv run pytest -m "not slow"

# PR 1 specific:
uv run pytest tests/test_give_item.py -v

# PR 2 specific:
uv run pytest tests/test_teach.py -v

# PR 3 specific:
uv run pytest tests/test_generational.py -v

# Smoke test (no LLM):
uv run main.py --no-llm --ticks 10 --agents 3

# Full LLM integration test after all 3 PRs:
uv run main.py --agents 3 --ticks 50 --seed 42 --save-log --verbose
# Verify: give_item and teach actions appear in logs
# Verify: trust changes logged after cooperation
# Verify: system prompt shows new actions
```

## Implementation Order

PR 1 (give_item) → PR 2 (teach) → PR 3 (generational tracking)

No hard dependencies between PRs, but this order builds complexity gradually. PR 3 is trivial and can be merged at any point.
