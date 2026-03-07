# Phase 3b Design: Communication + Trust + Conflict

**Date:** 2026-03-07
**Status:** Approved

---

## Overview

Phase 3b adds the first real social primitives to Emerge agents: the ability to **communicate** with each other and a **relationship/trust model** that persists across interactions.

Phase 3a gave agents personality and social perception (they can see each other). Phase 3b gives them a voice and memory of social outcomes.

---

## PR Split Rationale

Two atomic PRs:

1. **PR 1 — Communication:** `communicate` base action, `IncomingMessage` dataclass, message queuing in Oracle, Engine wiring, prompt updates.
2. **PR 2 — Trust + Conflict:** `Relationship` dataclass, trust update events triggered by communication and innovated aggressive actions.

This split keeps each PR reviewable and independently testable.

---

## Data Structures

### `IncomingMessage` (`simulation/message.py`)

```python
@dataclass
class IncomingMessage:
    sender: str      # agent name
    tick: int        # tick it was sent
    message: str     # free-text content
    intent: str      # one of VALID_INTENTS

VALID_INTENTS = {"share_info", "request_help", "warn", "trade_offer"}
```

Messages are stored on the **recipient** agent's `incoming_messages: list[IncomingMessage]`.
They are **cleared after the agent's `decide_action()` call** (consumed once, never persisted beyond the tick).

### `Relationship` (`simulation/relationship.py`)

```python
@dataclass
class Relationship:
    target: str
    trust: float = 0.0       # clamped [-1.0, 1.0]
    cooperations: int = 0
    conflicts: int = 0
    last_tick: int = 0
    bonded: bool = False
```

Status derived from trust:
- `> 0.6` → "friendly"
- `> 0.2` → "neutral"
- `> -0.3` → "wary"
- `<= -0.3` → "hostile"

Bonding triggers when `trust >= BONDING_TRUST_THRESHOLD (0.75)` AND `cooperations >= BONDING_COOPERATION_MINIMUM (3)`.

---

## Oracle Validation Rules for `communicate`

The Oracle validates meta-only (no LLM content inspection). Checks in order:

1. **Intent valid** — must be in `VALID_INTENTS`
2. **Rate limit** — one communication per agent per tick (`_communicated_this_tick` set)
3. **Energy** — sender must have `>= COMMUNICATE_ENERGY_COST (3)` energy
4. **Target exists** — target name must match an alive agent in `current_tick_agents`
5. **Range** — Manhattan distance must be `<= AGENT_VISION_RADIUS`

On success: deduct energy, queue `IncomingMessage` on target, add sender to rate-limit set.

---

## Trust Event Table

| Event | Delta | Who updates |
|-------|-------|-------------|
| Successful `communicate` | +0.05 sender→recipient | Oracle `_resolve_communicate()` |
| Aggressive innovation executed (victim) | −`trust_impact` (0.05–0.5) | Oracle `_resolve_custom_action()` |
| Aggressive innovation executed (attacker) | −`trust_impact * 0.5` | Oracle `_resolve_custom_action()` |

`trust_impact` is set by the Oracle validation LLM when it approves an innovation with `aggressive: true`.

---

## Conflict via `trust_impact` in Precedent

Aggression is **not a base action** — agents innovate it (e.g. `steal_food`, `attack`).

When the Oracle's innovation validation LLM approves an action, it may include:
```json
{
  "aggressive": true,
  "trust_impact": 0.3
}
```

This is stored in the precedent (`oracle.precedents["innovation:<name>"]`). When the action subsequently executes, `_resolve_custom_action()` applies the trust damage to victim and attacker using the stored values.

---

## Config Constants Added

```python
COMMUNICATE_ENERGY_COST = 3
BONDING_TRUST_THRESHOLD = 0.75
BONDING_COOPERATION_MINIMUM = 3
COMMUNICATE_TRUST_DELTA = 0.05
```

---

## Prompt Changes

**`prompts/agent/decision.txt`:** Adds `$incoming_messages` and `$relationships` sections (empty string = section omitted).

**`prompts/agent/system.txt`:** Adds `communicate` to the available base actions list with format and intent options.

---

## Engine Changes

Before the per-agent loop each tick:
- `oracle.current_tick_agents = alive_agents`
- `oracle._communicated_this_tick = set()`

After `agent.decide_action()` returns (before Oracle resolves):
- `agent.incoming_messages.clear()`
