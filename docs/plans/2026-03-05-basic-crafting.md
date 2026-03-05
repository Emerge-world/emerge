# Basic Crafting Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Agents can innovate CRAFTING actions that consume raw materials from inventory and produce new items, fully emergent — agents propose recipes, oracle validates plausibility, items consumed and produced on every execution.

**Architecture:** Extend `precedents["innovation:<name>"]` to store `requires` and `produces` dicts at approval time. `_resolve_custom_action` reads these to enforce item checks, consume materials, and add produced items. No new base action, no new class. Three oracle.py function changes, two prompt file edits, seven new tests.

**Tech Stack:** Python 3.12+, pytest — no new dependencies.

---

## Context for Implementer

Key design decisions (from DEC-018):
- Agent includes `produces: {"knife": 1}` in the `innovate` action JSON — they propose the recipe
- Items are consumed **every time** the crafting action is executed (not just once at discovery)
- When crafting fails due to missing materials, the oracle message is **generic** — no specific item names revealed (preserves emergence: agents must reason about their own inventory)
- `requires` is already checked at innovation approval time (existing code). We just also store it in the precedent so the executor can read it later.
- The existing `Inventory` class (`simulation/inventory.py`) has all the methods needed: `has()`, `remove()`, `add()`, `to_prompt()`.

Key files:
- `simulation/oracle.py` — all core logic (524 lines currently)
- `prompts/agent/system.txt` — agent decision prompt (innovate format)
- `prompts/oracle/innovation_system.txt` — oracle validation prompt
- `prompts/oracle/custom_action_system.txt` — oracle custom action prompt
- `tests/test_innovation.py` — existing innovation tests (418 lines)
- `project-cornerstone/00-master-plan/DECISION_LOG.md`
- `project-cornerstone/06-innovation-system/innovation-system_context.md`

Run tests with: `uv run pytest -m "not slow"` (always use `uv run`, never bare `python` or `pytest`)

---

## Task 1: Store `requires` and `produces` in the innovation precedent

**Files:**
- Modify: `simulation/oracle.py:399-422` (`_resolve_innovate`)
- Test: `tests/test_innovation.py` (append to existing file)

### Step 1: Write the failing tests

Append this class to the end of `tests/test_innovation.py`:

```python
# ---------------------------------------------------------------------------
# Crafting (DEC-018)
# ---------------------------------------------------------------------------

class TestCraftingPrecedentStorage:
    """_resolve_innovate must persist requires + produces in the innovation precedent."""

    def _innovate_make_knife(self, oracle, agent, tick=1):
        """Helper: agent innovates make_knife with requires+produces."""
        agent.inventory.add("stone", 3)  # agent must have the items to propose
        return oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve two stones into a sharp blade",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=tick,
        )

    def test_produces_stored_in_precedent(self):
        """After approval, precedent contains the produces dict."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        result = self._innovate_make_knife(oracle, agent)

        assert result["success"] is True
        precedent = oracle.precedents.get("innovation:make_knife", {})
        assert precedent.get("produces") == {"knife": 1}

    def test_requires_stored_in_precedent(self):
        """After approval, precedent contains the requires dict."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        self._innovate_make_knife(oracle, agent)

        precedent = oracle.precedents.get("innovation:make_knife", {})
        assert precedent.get("requires") == {"items": {"stone": 2}}

    def test_innovation_without_produces_stores_no_produces_key(self):
        """A normal (non-crafting) innovation must not get a produces key."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        oracle.resolve_action(
            agent,
            {"action": "innovate", "new_action_name": "fish", "description": "catch fish"},
            tick=1,
        )
        precedent = oracle.precedents.get("innovation:fish", {})
        assert "produces" not in precedent

    def test_produces_none_not_stored(self):
        """produces=None must not write a produces key."""
        world = _make_world()
        agent = _make_agent(world)
        oracle = _make_oracle(world)

        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "forage",
                "description": "gather mushrooms",
                "produces": None,
            },
            tick=1,
        )
        precedent = oracle.precedents.get("innovation:forage", {})
        assert "produces" not in precedent
```

### Step 2: Run to confirm failure

```bash
uv run pytest tests/test_innovation.py::TestCraftingPrecedentStorage -v
```

Expected: `FAILED` — `AssertionError` because `produces` key does not exist in precedent yet.

### Step 3: Implement — modify `_resolve_innovate` in `simulation/oracle.py`

Find the precedent registration block at lines ~403-409. Replace:

```python
        # Register the new action as a precedent
        self.precedents[f"innovation:{new_action_name}"] = {
            "creator": agent.name,
            "description": description,
            "tick_created": tick,
            "category": category,
        }
```

With:

```python
        # Register the new action as a precedent
        precedent_data = {
            "creator": agent.name,
            "description": description,
            "tick_created": tick,
            "category": category,
        }
        # Store requires + produces so _resolve_custom_action can handle crafting
        if isinstance(requires, dict):
            precedent_data["requires"] = requires
        produces = action.get("produces")
        if isinstance(produces, dict) and produces:
            precedent_data["produces"] = produces
        self.precedents[f"innovation:{new_action_name}"] = precedent_data
```

Note: `requires` is already bound earlier in the function (line ~339: `requires = action.get("requires")`), so no new variable needed.

### Step 4: Run tests to confirm pass

```bash
uv run pytest tests/test_innovation.py::TestCraftingPrecedentStorage -v
```

Expected: all 4 tests `PASSED`.

Also run existing tests to confirm no regression:

```bash
uv run pytest tests/test_innovation.py -v
```

Expected: all existing tests still pass.

### Step 5: Commit

```bash
git add simulation/oracle.py tests/test_innovation.py
git commit -m "feat(crafting): store requires+produces in innovation precedent"
```

---

## Task 2: Item check at execution time (fail-fast, generic message)

**Files:**
- Modify: `simulation/oracle.py:462-498` (`_resolve_custom_action`)
- Test: `tests/test_innovation.py` (append new class)

### Step 1: Write the failing tests

Append to `tests/test_innovation.py`:

```python
class TestCraftingExecution:
    """_resolve_custom_action must check, consume, and produce items for crafting actions."""

    def _setup_crafting(self, world=None, llm=None):
        """
        Return (oracle, agent) with 'make_knife' already innovated.
        make_knife: requires {items: {stone: 2}}, produces {knife: 1}
        LLM mock returns a valid custom-action result for execution.
        """
        world = world or _make_world()
        agent = _make_agent(world)
        agent.inventory.add("stone", 5)  # pre-load inventory

        # LLM: first call approves innovation, second judges the action
        if llm is None:
            llm = MagicMock()
            llm.last_call = None
            llm.generate_json.side_effect = [
                {"approved": True, "reason": "Makes sense.", "category": "CRAFTING"},
                {"success": True, "message": "You shaped the stones into a blade.", "effects": {"energy": -8}},
            ]

        oracle = _make_oracle(world, llm=llm)
        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve two stones into a blade",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=1,
        )
        return oracle, agent

    def test_crafting_fails_without_required_items(self):
        """Crafting action fails when agent lacks materials."""
        world = _make_world()
        agent = _make_agent(world)
        agent.inventory.add("stone", 5)

        llm = MagicMock()
        llm.last_call = None
        llm.generate_json.return_value = {"approved": True, "reason": "ok", "category": "CRAFTING"}
        oracle = _make_oracle(world, llm=llm)

        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve stones",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=1,
        )

        # Clear inventory so agent lacks stones
        agent.inventory.items.clear()

        result = oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)
        assert result["success"] is False

    def test_crafting_failure_message_does_not_reveal_item_names(self):
        """The failure message must be generic — no item name like 'stone' revealed."""
        world = _make_world()
        agent = _make_agent(world)
        agent.inventory.add("stone", 5)

        llm = MagicMock()
        llm.last_call = None
        llm.generate_json.return_value = {"approved": True, "reason": "ok", "category": "CRAFTING"}
        oracle = _make_oracle(world, llm=llm)

        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve stones",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=1,
        )
        agent.inventory.items.clear()

        result = oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)
        assert "stone" not in result["message"].lower()

    def test_crafting_item_check_before_llm_on_execution(self):
        """When items are missing at execution time, no LLM call is made."""
        world = _make_world()
        agent = _make_agent(world)
        agent.inventory.add("stone", 5)

        llm = MagicMock()
        llm.last_call = None
        # Only the innovation approval call; execution check must short-circuit
        llm.generate_json.return_value = {"approved": True, "reason": "ok", "category": "CRAFTING"}
        oracle = _make_oracle(world, llm=llm)

        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve stones",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=1,
        )
        call_count_after_innovation = llm.generate_json.call_count
        agent.inventory.items.clear()

        oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)
        # No additional LLM call should have been made
        assert llm.generate_json.call_count == call_count_after_innovation

    def test_crafting_consumes_items_on_success(self):
        """After successful crafting, required items are removed from inventory."""
        oracle, agent = self._setup_crafting()
        stone_before = agent.inventory.items.get("stone", 0)

        oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)

        stone_after = agent.inventory.items.get("stone", 0)
        assert stone_after == stone_before - 2

    def test_crafting_produces_item_in_inventory(self):
        """After successful crafting, the produced item appears in inventory."""
        oracle, agent = self._setup_crafting()

        oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)

        assert agent.inventory.items.get("knife", 0) == 1

    def test_crafting_no_llm_consumes_and_produces(self):
        """Without LLM, crafting still consumes and produces items."""
        world = _make_world()
        agent = _make_agent(world)
        agent.inventory.add("stone", 5)
        oracle = _make_oracle(world)  # no LLM

        oracle.resolve_action(
            agent,
            {
                "action": "innovate",
                "new_action_name": "make_knife",
                "description": "carve stones",
                "requires": {"items": {"stone": 2}},
                "produces": {"knife": 1},
            },
            tick=1,
        )
        stone_before = agent.inventory.items.get("stone", 0)
        oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)

        assert agent.inventory.items.get("stone", 0) == stone_before - 2
        assert agent.inventory.items.get("knife", 0) == 1

    def test_crafting_via_precedent_cache_also_consumes_produces(self):
        """The second execution (hits precedent cache) must also consume+produce."""
        oracle, agent = self._setup_crafting()

        # First execution: sets precedent
        oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)

        # Reload materials for second execution
        agent.inventory.add("stone", 5)
        knife_before = agent.inventory.items.get("knife", 0)
        stone_before = agent.inventory.items.get("stone", 0)

        # Second execution: hits precedent cache
        oracle.resolve_action(agent, {"action": "make_knife"}, tick=3)

        assert agent.inventory.items.get("stone", 0) == stone_before - 2
        assert agent.inventory.items.get("knife", 0) == knife_before + 1
```

### Step 2: Run to confirm failure

```bash
uv run pytest tests/test_innovation.py::TestCraftingExecution -v
```

Expected: most tests `FAILED` — items are not being consumed or produced yet; failure message may reveal item names.

### Step 3: Implement — modify `_resolve_custom_action` in `simulation/oracle.py`

Replace the entire `_resolve_custom_action` method (lines ~462–498):

```python
    def _resolve_custom_action(self, agent: Agent, action: dict, tick: int) -> dict:
        action_type = action.get("action")
        precedent_key = f"innovation:{action_type}"

        # Look up information about this action
        innovation = self.precedents.get(precedent_key, {})
        description = innovation.get("description", "unknown action")

        # Extract crafting recipe from stored innovation data
        required_items: dict = {}
        stored_requires = innovation.get("requires")
        if isinstance(stored_requires, dict):
            ri = stored_requires.get("items", {})
            if isinstance(ri, dict):
                required_items = ri
        produces: dict = innovation.get("produces") or {}

        # Fail fast if crafting items are missing — generic message, no item names revealed
        if required_items:
            for item, qty in required_items.items():
                try:
                    qty_int = int(qty)
                except (ValueError, TypeError):
                    qty_int = 1
                if not agent.inventory.has(item, qty_int):
                    msg = f"{agent.name} tried '{action_type}' but lacked the required materials."
                    self._log(tick, msg)
                    agent.add_memory(
                        f"I tried to '{action_type}' but I was missing materials. "
                        f"I need to gather more resources first."
                    )
                    return {"success": False, "message": msg, "effects": {}}

        # Check if there's already a precedent result for this specific situation
        situation_key = f"custom_action:{action_type}:tile:{self.world.get_tile(agent.x, agent.y)}"
        existing_result = self.precedents.get(situation_key)

        if existing_result:
            # Use precedent result (determinism)
            result = self._apply_custom_result(agent, action_type, existing_result, tick)
            self._apply_crafting_recipe(agent, action_type, required_items, produces, tick)
            return result

        if not self.llm:
            # Without LLM, generic effect
            result = {"success": True, "message": f"{agent.name} performed '{action_type}'.", "effects": {"energy": -5}}
            agent.modify_energy(-5)
            self._log(tick, result["message"])
            self._apply_crafting_recipe(agent, action_type, required_items, produces, tick)
            return result

        # Ask the oracle to determine the outcome
        oracle_result = self._oracle_judge_custom_action(agent, action, description, tick)

        if oracle_result:
            # Save as precedent for determinism
            self.precedents[situation_key] = oracle_result
            result = self._apply_custom_result(agent, action_type, oracle_result, tick)
            self._apply_crafting_recipe(agent, action_type, required_items, produces, tick)
            return result

        # Fallback
        agent.modify_energy(-5)
        msg = f"{agent.name} tried '{action_type}' with uncertain results."
        self._log(tick, msg)
        agent.add_memory(f"I performed '{action_type}' but I'm not sure of the outcome.")
        self._apply_crafting_recipe(agent, action_type, required_items, produces, tick)
        return {"success": True, "message": msg, "effects": {"energy": -5}}
```

Then add the new helper method `_apply_crafting_recipe` right after `_apply_custom_result` (around line ~516):

```python
    def _apply_crafting_recipe(
        self,
        agent: Agent,
        action_type: str,
        required_items: dict,
        produces: dict,
        tick: int,
    ) -> None:
        """Consume required items and add produced items for a crafting action."""
        # Consume
        for item, qty in required_items.items():
            try:
                qty_int = int(qty)
            except (ValueError, TypeError):
                qty_int = 1
            agent.inventory.remove(item, qty_int)

        # Produce
        for item, qty in produces.items():
            try:
                qty_int = int(qty)
            except (ValueError, TypeError):
                qty_int = 1
            added = agent.inventory.add(item, qty_int)
            if added > 0:
                agent.add_memory(
                    f"I crafted {added}x {item} via '{action_type}'. "
                    f"Inventory: {agent.inventory.to_prompt()}."
                )
```

### Step 4: Run tests to confirm pass

```bash
uv run pytest tests/test_innovation.py::TestCraftingExecution -v
```

Expected: all 7 tests `PASSED`.

Run full innovation test suite:

```bash
uv run pytest tests/test_innovation.py -v
```

Expected: all tests pass (existing + new).

Run smoke test:

```bash
uv run main.py --no-llm --ticks 5 --agents 1
```

Expected: exits normally, no crash.

### Step 5: Commit

```bash
git add simulation/oracle.py tests/test_innovation.py
git commit -m "feat(crafting): check, consume, and produce items in _resolve_custom_action"
```

---

## Task 3: Include `produces` in innovation validation prompt

**Files:**
- Modify: `simulation/oracle.py:520-551` (`_validate_innovation`)

This is a prompt-quality improvement — the oracle LLM can now judge whether `"stone → knife"` is physically plausible. No new tests needed (the existing LLM mock tests don't exercise prompt content).

### Step 1: Modify `_validate_innovation` signature and prompt

In `simulation/oracle.py`, update `_validate_innovation`:

```python
    def _validate_innovation(
        self, agent: Agent, action_name: str, description: str, tick: int = 0,
        produces: dict | None = None,
    ) -> dict:
        """Use the oracle LLM to validate whether an innovation is reasonable."""
        existing = ", ".join(f'"{a}"' for a in agent.actions)

        produces_text = ""
        if isinstance(produces, dict) and produces:
            produces_text = (
                f'\nThe agent claims this action produces: {produces}. '
                f'Is it physically plausible to produce these items from the declared inputs?'
            )

        prompt = f"""An agent named {agent.name} wants to invent a new action called "{action_name}".
Description: "{description}"

The agent is at position ({agent.x}, {agent.y}) on a tile of type "{self.world.get_tile(agent.x, agent.y)}".
The agent's stats: Life={agent.life}, Hunger={agent.hunger}, Energy={agent.energy}.
The agent already knows these actions: {existing}.

The world is a primitive survival setting (think early human civilization).
Is this innovation reasonable, feasible, and meaningfully different from existing actions?{produces_text}

Respond with JSON: {{"approved": true/false, "reason": "explanation", "category": "SURVIVAL|CRAFTING|EXPLORATION|SOCIAL"}}"""

        system = prompt_loader.load("oracle/innovation_system")
        result = self.llm.generate_json(prompt, system_prompt=system, temperature=0.3)

        if self.sim_logger and self.llm.last_call:
            lc = self.llm.last_call
            self.sim_logger.log_oracle_llm_call(
                tick=tick, context=f"Validate innovation '{action_name}' by {agent.name}",
                system_prompt=lc.get("system_prompt", ""),
                user_prompt=lc.get("user_prompt", ""),
                raw_response=lc.get("raw_response", ""),
                parsed_result=result,
            )

        if result and "approved" in result:
            return result
        return {"approved": True, "reason": "Oracle could not decide, defaulting to approved.", "category": "SURVIVAL"}
```

### Step 2: Update the call site in `_resolve_innovate`

Find the `_validate_innovation` call (line ~391):

```python
            validation = self._validate_innovation(agent, new_action_name, description, tick)
```

Replace with:

```python
            validation = self._validate_innovation(
                agent, new_action_name, description, tick,
                produces=action.get("produces"),
            )
```

### Step 3: Run tests to confirm no regression

```bash
uv run pytest tests/test_innovation.py -v
```

Expected: all tests pass. The `produces` parameter is optional and backward-compatible.

### Step 4: Commit

```bash
git add simulation/oracle.py
git commit -m "feat(crafting): pass produces to innovation validation prompt"
```

---

## Task 4: Update prompts

**Files:**
- Modify: `prompts/agent/system.txt`
- Modify: `prompts/oracle/innovation_system.txt`
- Modify: `prompts/oracle/custom_action_system.txt`

### Step 1: Update `prompts/agent/system.txt`

Change line 10 from:
```
- innovate: {"action": "innovate", "new_action_name": "...", "description": "...", "reason": "...", "requires": {"tile": "water|land|tree", "min_energy": <number>}}
  (requires is optional — only include fields that apply to your innovation)
```

To:
```
- innovate: {"action": "innovate", "new_action_name": "...", "description": "...", "reason": "...", "requires": {"tile": "water|land|tree", "min_energy": <number>, "items": {"stone": 2}}, "produces": {"knife": 1}}
  (requires and produces are optional. Use 'produces' when your innovation creates a new item from raw materials.)
```

Also update line 13 from:
```
For innovation actions you should not innovate something that is already available as a base action. Be creative and strategic about what new actions could help you survive better in this world. If your innovation only makes sense in a specific context (e.g. fishing requires water), include the relevant requires fields. Always explain your reasoning for innovating a new action and how it would help you in the current situation.
```

To:
```
For innovation actions you should not innovate something that is already available as a base action. Be creative and strategic about what new actions could help you survive better in this world. If your innovation only makes sense in a specific context (e.g. fishing requires water), include the relevant requires fields. If your innovation produces a physical item (e.g. make_knife produces a knife), include a produces field. Always explain your reasoning for innovating a new action and how it would help you in the current situation.
```

### Step 2: Update `prompts/oracle/innovation_system.txt`

Append to the file:

```
For CRAFTING innovations, also verify that the proposed 'produces' output is physically plausible given the 'requires.items' inputs (e.g., stone can become a knife; fruit cannot become metal). If produces is absent, infer whether the action should be CRAFTING or another category from the description.
```

### Step 3: Update `prompts/oracle/custom_action_system.txt`

Append to the file:

```
For crafting actions, determine only the energy cost of the physical labor. Do not include item consumption or item production in the effects dict — those are handled separately and deterministically.
```

### Step 4: Run smoke test

```bash
uv run main.py --no-llm --ticks 5 --agents 1
```

Expected: exits normally. No LLM prompt tests; prompt changes are validated by integration.

### Step 5: Commit

```bash
git add prompts/agent/system.txt prompts/oracle/innovation_system.txt prompts/oracle/custom_action_system.txt
git commit -m "feat(crafting): update agent and oracle prompts for crafting/produces field"
```

---

## Task 5: Update cornerstone documentation

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/06-innovation-system/innovation-system_context.md`

### Step 1: Add DEC-018 to DECISION_LOG.md

Read the file first, then append after the last decision entry:

```markdown
### DEC-018 — Basic Crafting as Innovatable Action (2026-03-05)

**Context:** Phase 2 requires crafting. DEC-017 added `requires.items` checks at innovation time but explicitly deferred item consumption. DEC-018 activates it.

**Decision:**
- Agents propose `produces: {item: qty}` in the `innovate` action JSON (fully emergent — no hardcoded recipes)
- `requires` and `produces` are stored in `precedents["innovation:<name>"]` at approval time
- On every execution of a crafting action: `requires.items` are checked → consumed from inventory; `produces` items added to inventory
- Failure message when materials missing is generic (no item names revealed) — preserves emergence
- Oracle `_validate_innovation` includes `produces` in the LLM prompt to check physical plausibility

**Implementation:** `_resolve_innovate` (precedent storage), `_resolve_custom_action` (item check + consumption + production via new `_apply_crafting_recipe` helper), `_validate_innovation` (produces in prompt).

**No new base action added.** Crafting is just an innovatable action with `produces`.
```

### Step 2: Update innovation-system_context.md

Find the crafting section in the context file and update it to reflect the new flow. Specifically:
- Document the `produces` field
- Document that `requires` is now stored in the innovation precedent (not just checked at proposal time)
- Document the generic failure message behavior
- Note `_apply_crafting_recipe` helper

### Step 3: Run full test suite one final time

```bash
uv run pytest -m "not slow" -v
```

Expected: all tests pass.

### Step 4: Commit

```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/06-innovation-system/innovation-system_context.md
git commit -m "docs(cornerstone): document crafting system as DEC-018"
```

---

## Final Verification

```bash
# 1. Full test suite
uv run pytest -m "not slow" -v

# 2. Smoke test (no LLM)
uv run main.py --no-llm --ticks 5 --agents 1

# 3. Integration test with LLM (if Ollama running)
uv run main.py --agents 2 --ticks 30 --seed 42 --verbose
# Watch for: "innovated 'make_X' [CRAFTING]" followed by execution that consumes items and adds produced items
```

**Success criteria:**
- `uv run pytest -m "not slow"` — all pass (20 existing + 11 new = 31 minimum)
- Smoke test exits without crash
- No existing test broken
