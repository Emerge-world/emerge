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

## Cooperation

### Cooperative actions

```python
# Require two agents to be adjacent and both choose to cooperate
"build_together"    # Build something that requires 2+ agents
"share_food"        # Give food from your inventory to another
"carry_together"    # Move heavy objects
"teach"             # Transmit an innovation to another agent
```

### Teaching innovations

```python
# Agent A knows "fish", agent B doesn't.
# A decides: {"action": "teach", "target": "Bruno", "skill": "fish"}
# Oracle verifies: A knows the action, B is adjacent, both spend energy
# Result: B adds "fish" to their repertoire
# The "recipe" (precedent) is copied too
ENERGY_COST_TEACH = 8   # for the teacher
ENERGY_COST_LEARN = 5   # for the student
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
