# Capability-Aware Prompt Surface Design

**Date:** 2026-03-27
**Status:** Approved

## Problem

The benchmark refactor introduces per-run capability ablations through typed runtime settings, but the agent prompt surface is still mostly static.

Today, several backend capabilities already change what the agent can do:

- action lists omit disabled actions
- planner invocation is skipped when explicit planning is off
- semantic compression is skipped when semantic memory is off
- oracle paths reject disabled innovation, item reflection, social, teach, and reproduction actions

However, the prompts still describe actions, context, and reflection paths that may no longer exist for a given benchmark arm. That violates the benchmark tracker rule that if a capability changes what the agent can do or see, the prompt must change too.

The current prompt implementation also has no composition layer:

- `simulation/prompt_loader.py` only loads and renders raw templates
- `prompts/agent/system.txt`, `decision.txt`, `planner_system.txt`, and `planner.txt` are treated as mostly fixed text
- `simulation/agent.py` and `simulation/planner.py` directly inject precomputed strings into those templates

Without a prompt-surface composition layer, capability ablations will drift between backend behavior and the cognitive surface seen by the model.

## Goal

Introduce a capability-aware prompt-surface layer that:

- keeps the existing prompt style and file layout under `prompts/`
- avoids duplicating `system.txt` and `decision.txt` into benchmark-specific variants
- composes executor and planner prompts from optional reusable blocks
- uses the same runtime capability policy already derived for backend execution
- removes disabled actions, context, and guidance from prompts deterministically
- adds golden tests for rendered prompt surfaces

The scope of this design is the agent cognition surface only:

- executor system prompt
- executor decision prompt
- planner system prompt
- planner user prompt
- planner observation text that feeds the planner prompt

This design does not change oracle semantics, benchmark manifest schema, or prompt wording unrelated to capability alignment.

## Decision

Adopt a single `PromptSurfaceBuilder` under `simulation/prompt_surface.py`.

This builder becomes the composition layer for all agent-facing prompts. It will:

- render the existing base templates through `simulation/prompt_loader.py`
- assemble capability-aware blocks and placeholders
- normalize optional-block whitespace so removed sections do not leave broken prompt structure
- be shared by executor and planner paths so both surfaces stay aligned

Rejected alternatives:

- building prompts entirely in Python strings: too much style drift away from `prompts/`
- duplicating full prompt templates per benchmark or capability set: violates the tracker constraints and invites divergence

## Design

### 1. Prompt Surface Boundary

Add `simulation/prompt_surface.py` with a `PromptSurfaceBuilder` that is initialized from the effective runtime policy already attached to an `Agent`.

Recommended constructor:

```python
PromptSurfaceBuilder(
    agent_settings: AgentRuntimeSettings,
    memory_settings: MemoryRuntimeSettings,
)
```

Recommended public methods:

- `build_executor_system(...) -> str`
- `build_executor_decision(...) -> str`
- `build_planner_system(...) -> str`
- `build_planner_prompt(...) -> str`
- `build_planner_observation_text(...) -> str`

The builder remains a pure formatting component:

- it does not mutate agent state
- it does not call the LLM
- it does not make benchmark-specific decisions
- it only converts runtime policy plus already computed agent context into prompt text

`simulation/prompt_loader.py` remains the low-level template loader and renderer. The builder uses it rather than replacing it.

### 2. Integration Points

`simulation/agent.py` should own one builder instance created from the agent's effective runtime settings:

```python
self.prompt_surface = PromptSurfaceBuilder(
    agent_settings=self.runtime_settings,
    memory_settings=self.memory_system.runtime_settings,
)
```

Executor integration:

- `_build_system_prompt()` delegates to `self.prompt_surface.build_executor_system(...)`
- `_build_decision_prompt(...)` delegates to `self.prompt_surface.build_executor_decision(...)`

Planner integration:

- `Planner` should accept the same builder instance during construction
- `Planner.plan(...)` should call `build_planner_system(...)` and `build_planner_prompt(...)`
- planner observation text should also be built through the prompt surface layer, not by a static helper that ignores capabilities

Recommended `Planner` constructor shape:

```python
Planner(llm, prompt_surface: PromptSurfaceBuilder)
```

This keeps executor and planner on the exact same capability policy and avoids duplicate gating logic.

### 3. Template Strategy

Keep the following base templates as the source of wording and style:

- `prompts/agent/system.txt`
- `prompts/agent/decision.txt`
- `prompts/agent/planner_system.txt`
- `prompts/agent/planner.txt`

Do not create full variants such as `system_no_social.txt` or `decision_no_planning.txt`.

Instead, introduce optional placeholders in those base templates and let the builder fill each placeholder with either:

- a rendered block
- an empty string

The builder must always supply every placeholder explicitly so `string.Template.substitute()` never fails when a block is disabled.

### 4. Placeholders and Blocks

The design introduces the following template placeholders.

#### 4.1 `prompts/agent/system.txt`

- `$strategic_capability_reminders`
- `$builtin_action_examples`
- `$reproduction_action_note`

`$builtin_action_examples` is the main capability-aware block for built-in action JSON examples. It allows actions to disappear cleanly without duplicating the whole prompt.

#### 4.2 `prompts/agent/decision.txt`

- `$social_context_block`
- `$planning_status_block`
- `$family_block`
- `$reproduction_hint_block`
- `$decision_reflection_questions`

#### 4.3 `prompts/agent/planner_system.txt`

- `$planner_capability_guidance`

#### 4.4 `prompts/agent/planner.txt`

- `$current_plan_block`
- `$planner_reflection_questions`

#### 4.5 Builder-level reusable blocks

The builder assembles the placeholders from a small set of reusable block producers:

- `innovation_reminder_block`
- `social_strategy_block`
- `teach_strategy_block`
- `reproduction_strategy_block`
- `innovate_action_example_block`
- `social_action_examples_block`
- `teach_action_example_block`
- `item_reflection_action_example_block`
- `social_context_block`
- `planning_status_block`
- `family_block`
- `reproduction_hint_block`
- `decision_reflection_questions_block`
- `planner_capability_guidance_block`
- `planner_reflection_questions_block`

The implementation does not need to expose these as public methods. They may be private helpers as long as the units stay clear and testable.

### 5. Capability Rules

The builder must apply the same hard prompt-surface rules described in `BENCHMARK_REFACTOR_TRACKER.md`.

#### 5.1 `explicit_planning = false`

Effects:

- do not render `CURRENT GOAL`
- do not render `ACTIVE SUBGOAL`
- do not render `PLAN STATUS`
- do not render `CURRENT PLAN` in planner prompts if a planner prompt is rendered in tests
- planner invocation remains disabled by runtime behavior

Prompt-surface requirements:

- executor decision prompt omits the full planning-status block
- planner-related reflection wording is not injected into executor prompts
- planner tests should continue to verify that no planner call happens when planning is off

#### 5.2 `semantic_memory = false`

Effects:

- omit `KNOWLEDGE`
- keep `RECENT EVENTS` when episodic memory exists
- skip semantic compression

Prompt-surface requirements:

- no separate prompt builder block should reintroduce semantic knowledge
- `memory.to_prompt()` remains the canonical source for memory text formatting
- builder tests must verify that episodic memory still appears when semantic memory is disabled

#### 5.3 `innovation = false`

Effects:

- remove `innovate` from action examples and capability reminders
- remove innovation-oriented reflection questions
- backend already blocks innovation

Prompt-surface requirements:

- executor system prompt must not show the `innovate` JSON example
- executor decision prompt must not mention blocked opportunities that suggest innovation
- planner system prompt must not recommend innovation as a long-horizon option
- planner user prompt must not ask whether a blocked opportunity suggests innovation

Important edge case:

- previously approved custom actions may still appear in `YOUR CUSTOM ACTIONS` if they are already available through persistence or other existing runtime state
- `innovation = false` only removes the ability to invent new actions, not the ability to use already-known custom actions

#### 5.4 `item_reflection = false`

Effects:

- remove `reflect_item_uses`
- remove the reflection hint about held items with unclear potential
- backend already blocks manual item reflection

Prompt-surface requirements:

- executor system prompt must not show the `reflect_item_uses` JSON example
- executor decision prompt must not recommend reflecting on carried items

#### 5.5 `social = false`

Effects:

- remove `communicate`
- remove `give_item`
- remove `teach`
- remove social context visibility
- backend already blocks social actions

Prompt-surface requirements:

- executor system prompt omits all social action examples
- executor decision prompt omits nearby agents, incoming messages, and relationships
- family remains governed separately by `reproduction`; social off alone does not imply reproduction off
- planner observation text omits nearby-agent information
- executor and planner reflection questions omit cooperation, teaching, social trust, and relationship framing

`teach = false` is dominated by `social = false`. No separate teach block is needed when the full social surface is disabled.

#### 5.6 `teach = false`

Effects:

- remove `teach` only
- keep `communicate` and `give_item` if `social = true`
- backend already blocks teaching

Prompt-surface requirements:

- executor system prompt omits the `teach` example only
- strategic reminders and reflection questions must not suggest teaching
- nearby agents, messages, and relationships remain visible if `social = true`

#### 5.7 `reproduction = false`

Effects:

- remove `reproduce`
- remove family context
- remove reproduction hints
- backend already blocks reproduction

Prompt-surface requirements:

- executor system prompt must not mention reproduction availability
- executor decision prompt omits `FAMILY`
- executor decision prompt omits `reproduction_hint`
- executor and planner reflection questions must not suggest reproduction
- planner system prompt must not recommend preparing for reproduction

### 6. Capability-aware Observation Text

`_build_observation_text(...)` in `simulation/agent.py` is currently planner-facing but capability-blind.

That is not acceptable for this refactor because planner prompts can still leak disabled context even if the outer planner template is cleaned up.

Therefore, the prompt-surface layer should own planner observation assembly.

Expected rules:

- `social = false` removes nearby-agent lines entirely
- `reproduction = false` removes family and reproduction-oriented hints if they are ever added to observation text later
- `innovation = false` does not remove already-known custom actions from observation text
- `explicit_planning = false` does not matter here because planner observation is only used when planning is active

The planner prompt must be capability-aware at both layers:

- the template blocks
- the observation text that fills those blocks

### 7. Whitespace and Prompt Normalization

Optional placeholders create a formatting risk: removing multiple adjacent blocks can leave awkward blank stretches or dangling section headers.

The builder should apply a deterministic final normalization step after template render:

- trim trailing whitespace on each line
- collapse 3 or more consecutive newline characters to 2
- preserve intentional single blank lines between sections
- strip leading and trailing blank lines from the final prompt

This keeps the prompts readable and keeps golden tests stable without changing the existing writing style.

### 8. Testing Strategy

Add dedicated prompt-surface golden tests in `tests/test_prompt_surface.py`.

Expected fixture directory:

- `tests/golden/prompts/`

Minimum golden coverage:

- `executor_system_full.txt`
- `executor_system_innovation_off.txt`
- `executor_system_social_off.txt`
- `executor_decision_full.txt`
- `executor_decision_planning_off.txt`
- `executor_decision_social_off.txt`
- `executor_decision_reproduction_off.txt`
- `planner_system_full.txt`
- `planner_system_innovation_off.txt`
- `planner_system_reproduction_off.txt`
- `planner_prompt_full.txt`
- `planner_prompt_social_off.txt`
- `planner_prompt_innovation_off.txt`

If the implementation exposes a planner prompt builder even when planning is disabled, it may also include:

- `planner_prompt_planning_off.txt`

Otherwise, explicit-planning-off coverage is satisfied by:

- golden diffs on executor decision prompts
- existing runtime tests that verify planner invocation is skipped

Golden tests should compare fully rendered prompt text, not only substring presence.

Targeted assertions should still exist for critical rules, especially:

- no `CURRENT GOAL`, `ACTIVE SUBGOAL`, `PLAN STATUS` when planning is off
- no `KNOWLEDGE` when semantic memory is off
- `RECENT EVENTS` survives when semantic memory is off and episodic memory exists
- no `innovate` example or innovation question when innovation is off
- no `reflect_item_uses` example or hint when item reflection is off
- no `communicate`, `give_item`, `teach`, nearby-agent context, messages, or relationships when social is off
- no `teach` when teach is off but social remains on
- no `reproduce`, `FAMILY`, or reproduction hint when reproduction is off

### 9. Required Before/After Examples

The implementation should include clear golden examples for at least:

- planning off
- innovation off
- social off

These should be easy to inspect in code review and should show meaningful surface changes rather than only a single missing line.

Expected example outcomes:

#### 9.1 Planning off

Before:

- executor decision prompt includes `CURRENT GOAL`, `ACTIVE SUBGOAL`, and `PLAN STATUS`

After:

- those sections are absent entirely
- the rest of the decision prompt remains structurally intact

#### 9.2 Innovation off

Before:

- executor system prompt includes the `innovate` JSON example
- planner and executor reflection text mention blocked opportunities that may suggest innovation

After:

- those action examples and questions disappear
- custom-action sections still remain if the agent already has custom actions

#### 9.3 Social off

Before:

- executor system prompt includes `communicate`, `give_item`, and `teach`
- executor decision prompt includes nearby agents, incoming messages, and relationships
- planner prompt and observation refer to nearby agents and relationship-oriented progress

After:

- those action examples disappear
- all social context sections disappear
- planner reflection wording no longer refers to cooperation, teaching, or relationships

### 10. Non-goals

This design does not:

- change the oracle action contract
- add benchmark-specific prompt variants
- change the memory compression pipeline beyond prompt-surface visibility
- redesign planner schema or executor schema
- tune prompt wording beyond the minimum needed to align capabilities

## Implementation Notes

Recommended implementation order:

1. Add `simulation/prompt_surface.py` and its block helpers
2. Update the four base templates with optional placeholders
3. Wire `Agent` executor prompt building through the builder
4. Wire `Planner` prompt building and observation text through the builder
5. Add golden tests and targeted assertions
6. Adjust any existing prompt tests that rely on removed static lines

## Risks and Mitigations

### Risk 1: Prompt drift between planner and executor

Mitigation:

- use one shared builder instance
- keep capability checks centralized in one module

### Risk 2: Optional placeholders leave malformed formatting

Mitigation:

- explicit empty-string placeholder filling
- final whitespace normalization
- goldens compare entire prompt text

### Risk 3: Capability rules get split between action lists and prompt wording

Mitigation:

- builder reads the same runtime settings already used to derive backend capability gates
- tests cover both action examples and context sections

### Risk 4: Over-scoping into a full prompt rewrite

Mitigation:

- preserve current template wording and structure wherever possible
- limit changes to placeholders and capability-specific blocks only

## Acceptance Criteria

This design is complete when the implementation delivers all of the following:

- a `PromptSurfaceBuilder` or equivalent under `simulation/prompt_surface.py`
- no duplicated full prompt templates per benchmark or capability set
- executor and planner prompts both become capability-aware
- planner observation text is capability-aware
- all tracker rules for planning, semantic memory, innovation, item reflection, social, teach, and reproduction are enforced in the prompt surface
- golden tests exist for rendered prompt text
- before/after prompt examples exist for planning off, innovation off, and social off
