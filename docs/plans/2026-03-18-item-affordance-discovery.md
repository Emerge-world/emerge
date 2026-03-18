# Item Affordance Discovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add first-time post-craft affordance discovery so crafted items can unlock concrete new actions, plus a manual `reflect_item_uses` action for discovering additional uses later.

**Architecture:** Keep items as inventory state and actions as normal innovations. Successful crafting of a new item type triggers one bounded Oracle affordance-discovery pass that proposes verb actions, validates them through the existing innovation path, and stores provenance (`origin_item`, discovery mode) on the resulting innovation precedents. Later discovery uses a built-in `reflect_item_uses` action that focuses on one held item and reuses the same Oracle helper without re-running automatic discovery.

**Tech Stack:** Python, pytest, Pydantic v2 structured outputs, prompt templates under `prompts/`, JSONL run events, existing Oracle innovation pipeline

---

### Task 1: Add The Public Action Contract For Manual Item Reflection

**Files:**
- Modify: `simulation/config.py`
- Modify: `simulation/schemas.py`
- Modify: `simulation/agent.py`
- Modify: `prompts/agent/system.txt`
- Modify: `prompts/agent/decision.txt`
- Modify: `data/schemas/base_world.yaml`
- Test: `tests/test_llm_client.py`
- Test: `tests/test_agent_prompts.py`
- Test: `tests/test_world_schema.py`

**Decision locked in:**
- New built-in action name: `reflect_item_uses`
- JSON contract: `{"action": "reflect_item_uses", "item": "<item_name>", "reason": "..."}`
- Energy cost constant: `ENERGY_COST_REFLECT_ITEM_USES = 5`
- Manual reflection only targets one held item at a time

**Step 1: Write the failing tests**

```python
# tests/test_llm_client.py
def test_returns_none_when_reflect_item_uses_is_missing_item(self):
    payload = '{"action": "reflect_item_uses", "reason": "find a new use"}'
    client = self._client_with_response(payload)
    assert client.generate_structured("prompt", AgentDecisionResponse) is None


# tests/test_agent_prompts.py
def test_system_prompt_documents_reflect_item_uses(self):
    agent = Agent(name="Ada", x=5, y=5)
    prompt = agent._build_system_prompt()
    assert '{"action": "reflect_item_uses"' in prompt
    assert '"item": "<item_name>"' in prompt


# tests/test_world_schema.py
def test_agent_costs_include_reflect_item_uses(self, schema):
    assert schema.agents["costs"]["reflect_item_uses"] == cfg.ENERGY_COST_REFLECT_ITEM_USES
```

**Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_llm_client.py::TestStructuredDecisionValidation::test_returns_none_when_reflect_item_uses_is_missing_item tests/test_agent_prompts.py::TestPersonalityInAgent::test_system_prompt_documents_reflect_item_uses tests/test_world_schema.py::TestWorldSchemaConsistency::test_agent_costs_include_reflect_item_uses -v`

Expected: FAIL because `reflect_item_uses` is not a known built-in contract yet.

**Step 3: Implement the minimal contract**

```python
# simulation/config.py
ENERGY_COST_REFLECT_ITEM_USES = 5

INITIAL_ACTIONS = [
    "move",
    "eat",
    "rest",
    "innovate",
    "pickup",
    "drop_item",
    "communicate",
    "give_item",
    "teach",
    "reflect_item_uses",
]


# simulation/schemas.py
_ACTION_REQUIRED_FIELDS = {
    ...
    "reflect_item_uses": ("item",),
}


# simulation/agent.py
costs = {
    ...
    "reflect_item_uses": ENERGY_COST_REFLECT_ITEM_USES,
}
```

Also:
- document `reflect_item_uses` in [`prompts/agent/system.txt`](/home/gusy/emerge/prompts/agent/system.txt)
- add one executor reflection hint in [`prompts/agent/decision.txt`](/home/gusy/emerge/prompts/agent/decision.txt): carrying a useful item may justify reflecting on new uses
- add `reflect_item_uses: 5` under `agents.costs` in [`data/schemas/base_world.yaml`](/home/gusy/emerge/data/schemas/base_world.yaml)

**Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_llm_client.py::TestStructuredDecisionValidation::test_returns_none_when_reflect_item_uses_is_missing_item tests/test_agent_prompts.py::TestPersonalityInAgent::test_system_prompt_documents_reflect_item_uses tests/test_world_schema.py::TestWorldSchemaConsistency::test_agent_costs_include_reflect_item_uses -v`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/config.py simulation/schemas.py simulation/agent.py prompts/agent/system.txt prompts/agent/decision.txt data/schemas/base_world.yaml tests/test_llm_client.py tests/test_agent_prompts.py tests/test_world_schema.py
git commit -m "feat: add reflect item uses action contract"
```

### Task 2: Build The Oracle Affordance Discovery Helper

**Files:**
- Modify: `simulation/schemas.py`
- Modify: `simulation/oracle.py`
- Create: `prompts/oracle/item_affordance_system.txt`
- Test: `tests/test_innovation.py`

**Decision locked in:**
- Discovery output is a bounded structured list of candidates, max 3
- Candidate shape: `action_name`, `description`, optional `tile`
- The helper auto-attaches `requires.items = {<origin_item>: 1}`
- The helper lowercases names, trims blanks, dedupes names, and skips already-known actions
- Discovery helper returns engine-ready payload entries shaped as:

```python
{
    "attempt": {
        "action": "innovate",
        "new_action_name": "cut_branches",
        "description": "cut branches from a tree",
        "requires": {"items": {"stone_knife": 1}, "tile": "tree"},
    },
    "result": {...innovation validation result...},
    "origin_item": "stone_knife",
    "discovery_mode": "auto",
    "trigger_action": "make_knife",
}
```

**Step 1: Write the failing tests**

```python
def test_discover_item_affordances_adds_tool_requirement():
    llm = MagicMock()
    llm.generate_structured.side_effect = [
        _typed({
            "candidates": [
                {"action_name": "cut_branches", "description": "cut branches from a tree", "tile": "tree"},
            ]
        }),
        _typed({"approved": True, "reason": "ok", "category": "CRAFTING"}),
    ]
    oracle = _make_oracle(_make_world(), llm=llm)
    agent = _make_agent(oracle.world)

    discovered = oracle._discover_item_affordances(
        agent, item_name="stone_knife", tick=2, discovery_mode="auto", trigger_action="make_knife"
    )

    assert discovered[0]["attempt"]["requires"] == {
        "items": {"stone_knife": 1},
        "tile": "tree",
    }


def test_discover_item_affordances_dedupes_known_actions():
    agent.actions.append("stab")
    ...
    names = [entry["result"]["name"] for entry in discovered]
    assert names == ["cut_branches"]
```

**Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_innovation.py::TestAffordanceDiscovery::test_discover_item_affordances_adds_tool_requirement tests/test_innovation.py::TestAffordanceDiscovery::test_discover_item_affordances_dedupes_known_actions -v`

Expected: FAIL because the helper, response schema, and prompt do not exist.

**Step 3: Implement the helper**

```python
# simulation/schemas.py
class ItemAffordanceCandidate(BaseModel):
    action_name: IdentifierText
    description: LongText
    tile: Optional[IdentifierText] = None


class ItemAffordanceDiscoveryResponse(BaseModel):
    candidates: list[ItemAffordanceCandidate] = Field(default_factory=list, max_length=3)


# simulation/oracle.py
def _discover_item_affordances(self, agent, *, item_name, tick, discovery_mode, trigger_action):
    if not self.llm:
        return []
    ...
    for candidate in parsed.candidates[:3]:
        name = candidate.action_name.strip().lower()
        if not name or name in agent.actions or name in seen_names:
            continue
        attempt = {
            "action": "innovate",
            "new_action_name": name,
            "description": candidate.description,
            "requires": {"items": {item_name: 1}, **({"tile": candidate.tile} if candidate.tile else {})},
        }
        result = self._resolve_innovation_candidate(...charge_energy=False...)
```

Prompt content in [`prompts/oracle/item_affordance_system.txt`](/home/gusy/emerge/prompts/oracle/item_affordance_system.txt):
- ask for concrete verbs, not `use_<item>` wrappers
- prohibit duplicates of already-known actions
- limit output to the most plausible 0-3 actions
- allow optional `tile` only when clearly necessary

**Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_innovation.py::TestAffordanceDiscovery::test_discover_item_affordances_adds_tool_requirement tests/test_innovation.py::TestAffordanceDiscovery::test_discover_item_affordances_dedupes_known_actions -v`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/schemas.py simulation/oracle.py prompts/oracle/item_affordance_system.txt tests/test_innovation.py
git commit -m "feat: add oracle item affordance discovery helper"
```

### Task 3: Reuse Innovation Registration And Auto-Trigger Discovery After First Craft

**Files:**
- Modify: `simulation/agent.py`
- Modify: `simulation/oracle.py`
- Test: `tests/test_innovation.py`

**Decision locked in:**
- Automatic discovery runs once per agent per produced item type
- Mark the item type as auto-reflected even if zero candidates are approved, so recrafting cannot spam retries
- Auto-derived innovations pay **no** extra `ENERGY_COST_INNOVATE`; only the crafting action cost applies
- Approved derived innovations store provenance in their innovation precedent:

```python
{
    "origin_item": "stone_knife",
    "discovery_mode": "auto",
}
```

**Step 1: Write the failing tests**

```python
def test_first_crafted_item_triggers_affordance_discovery_once():
    oracle, agent, llm = _setup_make_knife_then_affordance_flow()
    result = oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)
    assert [d["result"]["name"] for d in result["derived_innovations"]] == ["cut_branches"]


def test_recrafting_same_item_does_not_retrigger_auto_discovery():
    oracle, agent, llm = _setup_make_knife_then_affordance_flow()
    oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)
    calls_after_first_craft = llm.generate_structured.call_count
    agent.inventory.add("stone", 2)

    oracle.resolve_action(agent, {"action": "make_knife"}, tick=3)

    assert llm.generate_structured.call_count == calls_after_first_craft + 1  # custom action only, no new affordance pass


def test_auto_discovery_failure_does_not_break_crafting():
    ...
    result = oracle.resolve_action(agent, {"action": "make_knife"}, tick=2)
    assert result["success"] is True
    assert agent.inventory.items.get("stone_knife", 0) == 1
    assert result["derived_innovations"] == []
```

**Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_innovation.py::TestCraftedItemAffordances::test_first_crafted_item_triggers_affordance_discovery_once tests/test_innovation.py::TestCraftedItemAffordances::test_recrafting_same_item_does_not_retrigger_auto_discovery tests/test_innovation.py::TestCraftedItemAffordances::test_auto_discovery_failure_does_not_break_crafting -v`

Expected: FAIL because crafting does not yet trigger affordance discovery or track first-time item sources.

**Step 3: Implement the auto-trigger path**

```python
# simulation/agent.py
self.auto_reflected_items: set[str] = set()


# simulation/oracle.py
def _resolve_innovation_candidate(..., charge_energy: bool, provenance: dict | None = None) -> dict:
    # extracted from _resolve_innovate so direct innovate and derived innovate share checks,
    # validator calls, precedent writes, aggression metadata, and memory logging.


def _trigger_post_craft_affordances(self, agent, *, produced_items, tick, trigger_action):
    derived = []
    for item_name in produced_items:
        if item_name in agent.auto_reflected_items:
            continue
        agent.auto_reflected_items.add(item_name)
        derived.extend(
            self._discover_item_affordances(
                agent,
                item_name=item_name,
                tick=tick,
                discovery_mode="auto",
                trigger_action=trigger_action,
            )
        )
    return derived
```

Wire this immediately after successful crafting in `_resolve_custom_action()` and attach:

```python
result["derived_innovations"] = derived
```

Also add `auto_reflected_items` to `Agent.get_status()` as a sorted list so debug snapshots show whether the one-time trigger was consumed.

**Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_innovation.py::TestCraftedItemAffordances::test_first_crafted_item_triggers_affordance_discovery_once tests/test_innovation.py::TestCraftedItemAffordances::test_recrafting_same_item_does_not_retrigger_auto_discovery tests/test_innovation.py::TestCraftedItemAffordances::test_auto_discovery_failure_does_not_break_crafting -v`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/agent.py simulation/oracle.py tests/test_innovation.py
git commit -m "feat: auto-discover affordances after first craft"
```

### Task 4: Implement The Manual `reflect_item_uses` Oracle Path

**Files:**
- Modify: `simulation/oracle.py`
- Modify: `simulation/agent.py`
- Test: `tests/test_innovation.py`

**Decision locked in:**
- `reflect_item_uses` requires `item` to be present in inventory
- If the item is missing, return `success=False` and spend no energy
- If no LLM is available, return `success=False`, spend no energy, and leave state unchanged
- If the item is present and the LLM path runs, spend `ENERGY_COST_REFLECT_ITEM_USES` exactly once
- A manual reflection with zero approved actions is still `success=True` because the agent completed the reflection attempt

**Step 1: Write the failing tests**

```python
def test_reflect_item_uses_requires_item_in_inventory():
    oracle = _make_oracle(_make_world(), llm=MagicMock())
    agent = _make_agent(oracle.world)

    result = oracle.resolve_action(
        agent,
        {"action": "reflect_item_uses", "item": "stone_knife", "reason": "find another use"},
        tick=3,
    )

    assert result["success"] is False


def test_reflect_item_uses_can_add_new_action_after_auto_discovery():
    oracle, agent, llm = _setup_agent_with_stone_knife_and_prior_auto_discovery()
    energy_before = agent.energy

    result = oracle.resolve_action(
        agent,
        {"action": "reflect_item_uses", "item": "stone_knife", "reason": "look for another use"},
        tick=5,
    )

    assert result["success"] is True
    assert "stab" in agent.actions
    assert agent.energy == energy_before - ENERGY_COST_REFLECT_ITEM_USES


def test_reflect_item_uses_without_llm_fails_cleanly():
    oracle = _make_oracle(_make_world(), llm=None)
    agent = _make_agent(oracle.world)
    agent.inventory.add("stone_knife", 1)
    energy_before = agent.energy

    result = oracle.resolve_action(
        agent,
        {"action": "reflect_item_uses", "item": "stone_knife", "reason": "think"},
        tick=4,
    )

    assert result["success"] is False
    assert agent.energy == energy_before
```

**Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_innovation.py::TestManualItemReflection::test_reflect_item_uses_requires_item_in_inventory tests/test_innovation.py::TestManualItemReflection::test_reflect_item_uses_can_add_new_action_after_auto_discovery tests/test_innovation.py::TestManualItemReflection::test_reflect_item_uses_without_llm_fails_cleanly -v`

Expected: FAIL because the built-in action does not resolve yet.

**Step 3: Implement the manual path**

```python
def _resolve_reflect_item_uses(self, agent: Agent, action: dict, tick: int) -> dict:
    item_name = (action.get("item") or "").strip().lower()
    if not item_name or not agent.inventory.has(item_name, 1):
        return {"success": False, "message": "...", "effects": {}}
    if not self.llm:
        return {"success": False, "message": "...", "effects": {}}

    agent.modify_energy(-ENERGY_COST_REFLECT_ITEM_USES)
    derived = self._discover_item_affordances(
        agent,
        item_name=item_name,
        tick=tick,
        discovery_mode="manual",
        trigger_action="reflect_item_uses",
    )
    return {
        "success": True,
        "message": "...",
        "effects": {"energy": -ENERGY_COST_REFLECT_ITEM_USES},
        "derived_innovations": derived,
    }
```

Add a dispatch branch in `resolve_action()` immediately before custom-action fallback so `reflect_item_uses` is treated as built-in, not as an innovation name.

**Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_innovation.py::TestManualItemReflection::test_reflect_item_uses_requires_item_in_inventory tests/test_innovation.py::TestManualItemReflection::test_reflect_item_uses_can_add_new_action_after_auto_discovery tests/test_innovation.py::TestManualItemReflection::test_reflect_item_uses_without_llm_fails_cleanly -v`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/oracle.py simulation/agent.py tests/test_innovation.py
git commit -m "feat: add manual item reflection action"
```

### Task 5: Scope Custom-Action Precedents By Required Items When Present

**Files:**
- Modify: `simulation/oracle.py`
- Test: `tests/test_innovation.py`

**Decision locked in:**
- Keep legacy key shape for actions with no `requires.items`
- For actions with `requires.items`, append a stable sorted tool signature
- Exact shape:

```python
"custom_action:{action_type}:tile:{tile}:tools:{item_a}:{qty_a},{item_b}:{qty_b}"
```

Example:

```python
"custom_action:cut_branches:tile:tree:tools:stone_knife:1"
```

**Step 1: Write the failing tests**

```python
def test_custom_action_precedent_key_includes_required_items_signature():
    oracle, agent = _setup_cut_branches_innovation()
    oracle.resolve_action(agent, {"action": "cut_branches"}, tick=3)
    assert "custom_action:cut_branches:tile:tree:tools:stone_knife:1" in oracle.precedents


def test_actions_without_required_items_keep_legacy_precedent_key():
    ...
    oracle.resolve_action(agent, {"action": "fish"}, tick=2)
    assert "custom_action:fish:tile:water" in oracle.precedents
```

**Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_innovation.py::TestCustomActionPrecedentKeys::test_custom_action_precedent_key_includes_required_items_signature tests/test_innovation.py::TestCustomActionPrecedentKeys::test_actions_without_required_items_keep_legacy_precedent_key -v`

Expected: FAIL because `_resolve_custom_action()` still hardcodes the old tile-only key.

**Step 3: Implement the key helper**

```python
def _custom_action_situation_key(self, action_type: str, tile: str, required_items: dict[str, int]) -> str:
    if not required_items:
        return f"custom_action:{action_type}:tile:{tile}"
    parts = [f"{item}:{int(qty)}" for item, qty in sorted(required_items.items())]
    return f"custom_action:{action_type}:tile:{tile}:tools:{','.join(parts)}"
```

Replace the inline `situation_key` construction in `_resolve_custom_action()` with this helper.

**Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_innovation.py::TestCustomActionPrecedentKeys::test_custom_action_precedent_key_includes_required_items_signature tests/test_innovation.py::TestCustomActionPrecedentKeys::test_actions_without_required_items_keep_legacy_precedent_key -v`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/oracle.py tests/test_innovation.py
git commit -m "fix: scope custom action precedents by required items"
```

### Task 6: Emit Derived Innovation Events And Preserve Analytics

**Files:**
- Modify: `simulation/event_emitter.py`
- Modify: `simulation/engine.py`
- Test: `tests/test_event_emitter.py`
- Test: `tests/test_engine_innovation_events.py`
- Test: `tests/test_metrics_builder.py`
- Test: `tests/test_ebs_builder.py`

**Decision locked in:**
- Do **not** add a new run-event type in v1
- Reuse `innovation_attempt` and `innovation_validated` for derived item-based innovations
- Extend those event payloads with optional extra fields:
  - `description`
  - `origin_item`
  - `discovery_mode`
  - `trigger_action`
- Existing metrics and EBS builders should continue to work by ignoring unknown fields

**Step 1: Write the failing tests**

```python
# tests/test_engine_innovation_events.py
def test_auto_discovered_innovations_emit_attempt_and_validated_events(...):
    ...
    attempts = [e for e in events if e["event_type"] == "innovation_attempt" and e["payload"]["name"] == "cut_branches"]
    validated = [e for e in events if e["event_type"] == "innovation_validated" and e["payload"]["name"] == "cut_branches"]
    assert len(attempts) == 1
    assert len(validated) == 1


# tests/test_event_emitter.py
def test_emit_innovation_validated_includes_origin_metadata(...):
    em.emit_innovation_validated(
        3, "Ada", {"success": True, "name": "cut_branches", "category": "CRAFTING"},
        requires={"items": {"stone_knife": 1}},
        description="cut branches from a tree",
        origin_item="stone_knife",
        discovery_mode="auto",
        trigger_action="make_knife",
    )
    ...
    assert payload["origin_item"] == "stone_knife"


# tests/test_metrics_builder.py
def test_metrics_builder_counts_item_derived_innovation_events(tmp_path):
    ...
    assert summary["innovations"]["approved"] == 1
```

**Step 2: Run the focused tests to verify they fail**

Run: `uv run pytest tests/test_event_emitter.py::TestInnovationEvents::test_emit_innovation_validated_includes_origin_metadata tests/test_engine_innovation_events.py::TestEngineInnovationEventWiring::test_auto_discovered_innovations_emit_attempt_and_validated_events tests/test_metrics_builder.py::TestMetricsBuilder::test_metrics_builder_counts_item_derived_innovation_events -v`

Expected: FAIL because the engine only emits innovation events for direct `innovate` actions.

**Step 3: Implement the event reuse**

```python
# simulation/event_emitter.py
def emit_innovation_validated(..., requires=None, produces=None, description=None,
                              origin_item=None, discovery_mode=None, trigger_action=None):
    self._emit("innovation_validated", tick, {
        ...
        "description": description,
        "origin_item": origin_item,
        "discovery_mode": discovery_mode,
        "trigger_action": trigger_action,
    }, agent_id=agent_name)


# simulation/engine.py
for entry in result.get("derived_innovations", []):
    attempt = entry["attempt"]
    validation = entry["result"]
    self.event_emitter.emit_innovation_attempt(tick, agent.name, attempt)
    self.event_emitter.emit_innovation_validated(
        tick,
        agent.name,
        validation,
        requires=attempt.get("requires"),
        produces=attempt.get("produces"),
        description=attempt.get("description"),
        origin_item=entry.get("origin_item"),
        discovery_mode=entry.get("discovery_mode"),
        trigger_action=entry.get("trigger_action"),
    )
```

If an approved derived action is later executed, the existing `custom_action_executed` event path should already capture it because the action name is now present in `agent.actions`.

**Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_event_emitter.py::TestInnovationEvents::test_emit_innovation_validated_includes_origin_metadata tests/test_engine_innovation_events.py::TestEngineInnovationEventWiring::test_auto_discovered_innovations_emit_attempt_and_validated_events tests/test_metrics_builder.py::TestMetricsBuilder::test_metrics_builder_counts_item_derived_innovation_events tests/test_ebs_builder.py::TestEBSBuilder::test_item_derived_innovation_with_origin_metadata_still_counts -v`

Expected: PASS

**Step 5: Commit**

```bash
git add simulation/event_emitter.py simulation/engine.py tests/test_event_emitter.py tests/test_engine_innovation_events.py tests/test_metrics_builder.py tests/test_ebs_builder.py
git commit -m "feat: emit item derived innovation events"
```

### Task 7: Update Cornerstone Docs And Decision Log

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/00-master-plan/MASTER_PLAN.md`
- Modify: `project-cornerstone/03-agents/agents_context.md`
- Modify: `project-cornerstone/04-oracle/oracle_context.md`
- Modify: `project-cornerstone/06-innovation-system/innovation-system_context.md`
- Modify: `project-cornerstone/10-testing/testing_context.md`
- Modify: `docs/plans/2026-03-18-item-affordance-discovery-design.md`

**Decision locked in:**
- Add a new decision log entry for item affordance discovery
- Record that innovation metrics now include item-derived actions because the engine re-emits standard innovation events
- Document the once-per-item auto-trigger and the manual `reflect_item_uses` follow-up path

**Step 1: Write the failing doc checks**

```bash
rg -n "reflect_item_uses|origin_item|item affordance|auto-reflected" project-cornerstone docs/plans/2026-03-18-item-affordance-discovery-design.md
```

Expected: missing references in cornerstone docs before editing.

**Step 2: Update the docs**

Required edits:
- [`project-cornerstone/00-master-plan/DECISION_LOG.md`](/home/gusy/emerge/project-cornerstone/00-master-plan/DECISION_LOG.md)
  - add a new `DEC-0XX` entry describing:
    - one-time auto discovery on first craft of an item type
    - manual `reflect_item_uses` for later discovery
    - no extra energy for auto-derived innovations
    - standard innovation event reuse for analytics
- [`project-cornerstone/00-master-plan/MASTER_PLAN.md`](/home/gusy/emerge/project-cornerstone/00-master-plan/MASTER_PLAN.md)
  - update the implemented innovation/crafting reality so crafted tools can unlock follow-on actions
  - note that existing innovation metrics include item-derived discoveries via normal innovation events
- [`project-cornerstone/03-agents/agents_context.md`](/home/gusy/emerge/project-cornerstone/03-agents/agents_context.md)
  - document `reflect_item_uses` as a built-in action
  - mention the per-agent `auto_reflected_items` tracking
- [`project-cornerstone/04-oracle/oracle_context.md`](/home/gusy/emerge/project-cornerstone/04-oracle/oracle_context.md)
  - document Oracle affordance discovery helper and tool-aware custom-action precedent keys
- [`project-cornerstone/06-innovation-system/innovation-system_context.md`](/home/gusy/emerge/project-cornerstone/06-innovation-system/innovation-system_context.md)
  - replace the missing craft-to-use gap with the implemented craft -> discover -> use loop
- [`project-cornerstone/10-testing/testing_context.md`](/home/gusy/emerge/project-cornerstone/10-testing/testing_context.md)
  - add coverage expectations for affordance discovery, auto-trigger idempotence, and manual reflection
- [`docs/plans/2026-03-18-item-affordance-discovery-design.md`](/home/gusy/emerge/docs/plans/2026-03-18-item-affordance-discovery-design.md)
  - update status or notes if the implementation diverges in any small way from the design

**Step 3: Verify the docs mention the new model**

Run: `rg -n "reflect_item_uses|origin_item|item affordance|auto-reflected|craft -> discover -> use" project-cornerstone docs/plans/2026-03-18-item-affordance-discovery-design.md`

Expected: matches in all updated cornerstone areas.

**Step 4: Commit**

```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/00-master-plan/MASTER_PLAN.md project-cornerstone/03-agents/agents_context.md project-cornerstone/04-oracle/oracle_context.md project-cornerstone/06-innovation-system/innovation-system_context.md project-cornerstone/10-testing/testing_context.md docs/plans/2026-03-18-item-affordance-discovery-design.md
git commit -m "docs: record item affordance discovery architecture"
```

### Final Verification

Run the feature-focused suite first:

```bash
uv run pytest tests/test_innovation.py tests/test_llm_client.py tests/test_agent_prompts.py tests/test_world_schema.py tests/test_event_emitter.py tests/test_engine_innovation_events.py tests/test_metrics_builder.py tests/test_ebs_builder.py -v
```

Expected:
- all targeted affordance-discovery and event-wiring tests pass
- no regression in direct innovation, crafting, or prompt validation behavior

Then run the required project smoke suite:

```bash
uv run pytest -m "not slow"
```

Expected: PASS

Before claiming completion, use `superpowers:verification-before-completion`.
