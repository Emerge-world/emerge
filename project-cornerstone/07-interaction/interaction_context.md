# 07 — Social Interaction (Phase 3)

> This module is NOT implemented until Phases 1 and 2 are stable.

## Concept

Agents can perceive, communicate and cooperate/compete with other agents.

## Social perception

When an agent "sees" another within their vision radius:

```python
# Add to nearby_tiles an "agents_nearby" field
nearby_info = {
    "tiles": [...],
    "agents_nearby": [
        {
            "name": "Bruno",
            "position": (12, 8),
            "distance": 2,
            "visible_stats": {
                # They don't see exact stats, only general state
                "looks_hungry": agent.hunger > 50,
                "looks_tired": agent.energy < 30,
                "looks_hurt": agent.life < 50,
            }
        }
    ]
}
```

## Communication

### Proposed model: free message

```python
# New action: "communicate"
{
    "action": "communicate",
    "target": "Bruno",           # target agent (must be in range)
    "message": "I found fruit trees to the north",
    "intent": "share_info"       # share_info | request_help | warn | trade
}
```

The receiving agent gets the message on their next tick as part of their perception:

```
INCOMING MESSAGES:
- Ada says: "I found fruit trees to the north" (intent: share_info)
```

### Language evolution (Phase 4)

In Phase 3 agents speak in natural language. In Phase 4, we can experiment with:
- Limited tokens per message (force compression)
- Invent their own "words"
- Misunderstandings based on distance

## Cooperation *(Phase 3c — Implemented)*

### `give_item` action

```python
# Transfer any inventory item to an adjacent agent (manhattan dist ≤ 1)
# Format: {"action": "give_item", "target": "<name>", "item": "<item>", "quantity": 1, "reason": "..."}
# Validations: target alive, adjacent, giver has item+quantity, target has free space, giver energy ≥ 2
# Effects:
#   - item removed from giver, added to target
#   - giver.energy -= 2
#   - target.update_relationship(giver, +0.15 trust, is_cooperation=True)
#   - both agents get episodic memory
GIVE_ITEM_ENERGY_COST = 2
GIVE_ITEM_TRUST_DELTA = 0.15
```

### `teach` action *(Phase 3c — DEC-024: no LLM call)*

```python
# Copy an owned innovation to a visible agent (dist ≤ AGENT_VISION_RADIUS)
# Format: {"action": "teach", "target": "<name>", "skill": "<innovation_name>", "reason": "..."}
# Validations: target alive, within vision range, teacher knows skill (precedent exists),
#              skill not in BASE_ACTIONS, learner doesn't already know it,
#              teacher energy ≥ 8, learner energy ≥ 5
# Effects:
#   - teacher.energy -= 8, learner.energy -= 5
#   - target.actions.append(skill)  # learner gains the action
#   - both agents get +0.20 trust toward each other
#   - both get episodic memory
# No LLM call — deterministic precedent copy
TEACH_ENERGY_COST_TEACHER = 8
TEACH_ENERGY_COST_LEARNER = 5
TEACH_TRUST_DELTA = 0.20
```

## Conflict

### Resource competition

When two agents try to eat the same resource on the same tick:
- The oracle processes actions in order
- The first one processed eats, the second fails
- In future: priority system (hungriest has preference)

### Aggression (optional, evaluate if it emerges naturally)

Don't implement aggression as a base action. If an agent innovates it, the oracle evaluates it:
- High energy required
- Risk of damage for the attacker too
- Social consequences (other agents remember)

## Relationship system (Phase 3+)

```python
class Relationship:
    target: str          # name of the other agent
    trust: float         # -1.0 to 1.0
    interactions: int    # number of interactions
    last_interaction: int  # tick
    
    # Trust rises with: cooperation, sharing, teaching
    # Trust falls with: competing, stealing, aggression, lying
```

## Considerations for Claude Code

- Social interaction DOUBLES LLM calls (decide + communicate + respond).
- Need to optimize before Phase 3: batch calls, faster models, or limit communications.
- Interaction tests need minimum 2 agents. Mock one as "scripted" and test the other.
- Main risk is that agents talk but say nonsense. Evaluate communication quality.

## Proto-language v1 (deterministic, constrained)

### Message format
- Backward compatible: keep `message` (free text).
- Optional structured compact form: `message_tokens: list[str]`.
- Oracle enforces `COMMUNICATE_MAX_TOKENS` budget when `message_tokens` is provided.

### Per-agent language state
- Each agent has a lexicon map (`symbol -> meaning`) with:
  - confidence in `[0,1]`
  - usage count
  - owned/not-owned marker
- Agents track recently learned symbols for prompt context.

### Oracle communication resolution rules (v1)
- Compute distance using Manhattan metric.
- Compute shared-symbol overlap from sender/receiver lexicons.
- Derive misunderstanding probability from distance (+) and overlap (-).
- Apply deterministic hash roll (`tick + sender + receiver + tokens`) to decide misunderstanding.
- Store both raw and interpreted message in receiver inbox/memory.

### Observability metrics
- `symbol_adoptions`: newly learned symbols per tick/run.
- `misunderstanding_rate`: misunderstood / total communications.
- `shared_vocabulary_size`: overlap observed per communication.
- Run-level hook: `language_tick_metrics` (mean shared vocabulary + mean lexicon size).
