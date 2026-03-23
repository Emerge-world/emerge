# Item Affordance Discovery Design

- **Date:** 2026-03-18
- **Status:** Implemented (2026-03-23) — see DEC-045 in DECISION_LOG.md
- **Audience:** Emerge maintainers working on innovation, oracle action resolution, prompts, and tests
- **Primary goal:** Let crafted items unlock concrete new actions without introducing a separate item-use action system
- **Focus:** Preserve the existing innovation architecture while adding a deterministic bridge from crafted tools to newly available verb actions

## 1. Problem Statement

The current crafting loop can create useful inventory items such as a stone knife, but those items do not expand what the agent can do next.

Today:

- crafting actions can consume materials and produce inventory items
- approved innovations already become executable actions
- produced items remain passive inventory state unless a built-in action already knows how to consume them

That leaves an important gap:

1. tools and crafted items exist, but they do not naturally create new affordances
2. the issue is not missing generic `use_<item>` actions, but missing concrete verbs such as `stab` or `cut_branches`
3. the current precedent model can also over-generalize outcomes if tool possession is not represented in context

## 2. Design Goals

The feature should:

1. turn newly crafted items into a source of new possible actions
2. keep actions verb-shaped, not item-shaped
3. reuse the normal innovation validation and precedent pipeline
4. require the enabling tool at execution time
5. preserve agent-local discovery and existing `teach` behavior
6. degrade safely when the LLM path fails

The feature should not:

- auto-register generic `use_<item>` actions
- introduce a hardcoded affordance table for each tool
- make item-derived actions globally known to all agents
- let tool-derived actions remain usable after the tool is lost
- repeatedly auto-trigger discovery every time the same item is crafted

## 3. Approaches Considered

### Option A: Auto-create `use_<item>` actions

Example: crafting `stone_knife` creates `use_stone_knife`.

**Pros**

- easy to explain
- closely matches the original issue wording

**Cons**

- too vague to express meaningful affordances
- creates awkward action names instead of useful verbs
- duplicates the existing innovation model rather than extending it

### Option B: Hardcoded affordance registry

Example: `stone_knife -> [stab, cut_branches]`.

**Pros**

- deterministic and simple to test
- easy to control output shape

**Cons**

- works against the emergence goal
- becomes a growing manual ruleset
- pushes design work into code instead of the innovation system

### Option C: Post-craft affordance discovery through normal innovations

After crafting a novel item, run one immediate reflection pass to propose concrete new verbs, then validate them through the existing innovation path.

**Pros**

- best fit with the current architecture
- keeps items as state and actions as verbs
- preserves emergence while staying bounded
- reuses existing approval, storage, and teaching mechanisms

**Cons**

- adds one new LLM-assisted bridge in the crafting flow
- requires tighter precedent context for tool-dependent actions

## 4. Chosen Direction

Adopt **Option C**.

When an agent successfully crafts a new inventory item type for the first time, the system should immediately reflect on what new actions that item enables. Those candidate actions should then be validated exactly like any other innovation. Approved candidates become normal actions owned by that agent.

This keeps the domain model clean:

- items stay in inventory
- actions stay as named verbs
- affordance discovery becomes the bridge between the two

## 5. Behavior Model

### Automatic discovery trigger

Run affordance discovery only when all of the following are true:

- a crafting action succeeds
- the crafting result produced at least one inventory item
- at least one produced item type is new to that agent as a crafted affordance source

Automatic discovery should happen only once per agent per produced item type.

Example:

- Ada crafts `stone_knife` for the first time -> trigger discovery
- Ada crafts another `stone_knife` later -> do not auto-trigger again

### What discovery produces

The reflection step should propose concrete verb actions enabled by the produced item in context.

Examples:

- `stone_knife` -> `stab`, `cut_branches`
- `rope` -> `tie_bundle`, `climb_safely`

The system should not propose generic wrappers like:

- `use_stone_knife`
- `use_rope`

### How discovered actions are admitted

Every discovered candidate must go through the normal innovation validation path:

1. discard blank or duplicate names
2. validate through the Oracle innovation validator
3. if approved, register as a normal innovation in `agent.actions`
4. persist normal `innovation:<action_name>` precedent data

The discovery bridge proposes candidates. It does not auto-approve them.

### Execution gating

Derived actions must record the enabling tool in their requirements, typically via `requires.items`.

Example:

```json
{
  "action": "cut_branches",
  "requires": {
    "items": {"stone_knife": 1}
  }
}
```

This ensures:

- the action can only succeed while the tool is still held
- losing the tool does not remove the action name, but it does block execution deterministically
- the behavior remains compatible with existing crafting prerequisite checks

### Ownership and transfer

Discovery is agent-local.

If Ada discovers `cut_branches` from a `stone_knife`, Bob does not gain that action automatically. Bob only gains it by:

- crafting and discovering it himself
- receiving it through `teach`

This preserves the current social learning model.

### Later re-reflection

After the first automatic discovery for an item type, agents may still discover additional uses later through an explicit reflection-style action.

That later path should:

- be intentional, not automatic
- use currently held items as reflection input
- allow discovery of additional verbs not found in the first pass
- remain bounded to avoid spam

The first iteration should introduce this explicit path as the only supported way to discover more uses after the initial automatic trigger.

## 6. Architecture and Component Changes

### `simulation/oracle.py`

- add a post-craft affordance hook after successful crafting results are known
- detect whether produced items include first-time affordance sources for the current agent
- run a bounded affordance reflection pass for eligible items
- route candidate actions through the existing innovation validation logic
- enrich derived innovation precedent data with provenance such as `origin_item` or `derived_from_items`

### `simulation/agent.py`

- expose the later explicit reflection action in prompts and available actions
- include enough inventory and custom-action context for the model to reason about item-enabled opportunities
- track which item types have already triggered automatic affordance discovery for that agent

### Prompt layer

- add a dedicated Oracle prompt for item affordance discovery, focused on short lists of concrete verbs
- update agent prompts so the later explicit reflection action is described clearly and does not compete with normal innovation unless useful

### Precedent context

Tool-dependent actions should not share the same cached outcome as tool-free actions where the tool materially changes plausibility or effects.

The precedent strategy should therefore incorporate relevant tool context for item-derived actions, or another equivalent deterministic discriminator, so outcomes like `cut_branches` with and without `stone_knife` do not collapse into one precedent entry.

## 7. Failure Handling and Invariants

Failure rules:

- if the post-craft affordance reflection fails, crafting still succeeds
- if the reflection returns invalid candidates, ignore them safely
- if innovation validation rejects a candidate, skip it without affecting the crafted item
- if the tool is absent later, the derived action fails before any LLM call

Preserved invariants:

- LLM failure must never crash the simulation
- Oracle remains the authority for action admission and execution
- dead agents never act
- repeated identical contexts should stay deterministic once precedents exist

## 8. Testing Plan

Core tests should cover:

1. successful first craft of a new item type triggers exactly one automatic affordance discovery pass
2. approved derived actions are added to the crafting agent as normal innovations
3. derived innovation precedent data records provenance and tool requirement information
4. recrafting the same item type does not auto-trigger discovery again
5. explicit later reflection can add a new item-enabled action after the first automatic pass
6. executing a derived action fails deterministically when the required tool is missing
7. affordance reflection failure does not break crafting or inventory mutation
8. duplicate candidates are ignored safely

## 9. Acceptance Criteria

- [ ] Crafting a new item type for the first time can immediately unlock one or more concrete verb actions
- [ ] Those actions are validated through the normal innovation path rather than auto-approved
- [ ] Derived actions retain a tool requirement so they depend on holding the relevant item later
- [ ] Automatic discovery runs only once per agent per produced item type
- [ ] Agents can later reflect again to discover additional uses intentionally
- [ ] Tests cover the craft -> discover -> use round-trip and failure cases with mocked LLM behavior
