# 06 — Innovation System

## Concept

Innovation is the heart of emergence. Agents can invent new actions that didn't exist in the original code. The oracle validates whether they make sense and establishes their effects.

## Current State (Phase 0)

1. Agent decides `{"action": "innovate", "new_action_name": "fish", "description": "catch fish from water"}`
2. Oracle validates with LLM: is it reasonable?
3. If yes: `"fish"` is added to the agent's repertoire
4. When the agent uses `"fish"`, the oracle determines the effect with LLM
5. The effect is saved as a precedent for future times

### Known issues

1. **Redundant innovations**: An agent can invent "gather_fruit" when "eat" already exists.
2. **No requirements**: Inventing "build_house" without having wood doesn't make sense.
3. **Unbalanced effects**: The LLM can give effects that are too powerful or useless.
4. **No material cost**: Innovating only costs energy, not resources.

## Phase 1 — Structured Innovation

### Innovation Request Format

```json
{
    "action": "innovate",
    "new_action_name": "build_shelter",
    "description": "Build a basic shelter using nearby materials for protection",
    "requires": {
        "tile": "forest",
        "nearby_resource": "wood",
        "min_energy": 30
    },
    "expected_effect": "protection from weather, place to rest safely"
}
```

### Oracle Validation Checklist

El oráculo verifica antes de llamar al LLM:

```python
def validate_innovation_prereqs(agent, action, world):
    checks = []
    
    # 1. Is the name unique?
    if action["new_action_name"] in agent.actions:
        return False, "Action already exists"
    
    # 2. Does it have enough energy?
    if agent.energy < ENERGY_COST_INNOVATE:
        return False, "Not enough energy"
    
    # 3. Is the name reasonable? (not empty, not too long, alphanumeric)
    name = action["new_action_name"]
    if not name or len(name) > 30 or not name.replace("_", "").isalnum():
        return False, "Invalid action name"
    
    return True, "Prereqs OK"
```

Then the LLM validates the semantic part (is it physically possible? does it make sense?).

### Innovation Categories

To guide the LLM, we classify innovations into categories:

```
SURVIVAL    → fish, gather_berries, find_water, hunt
CRAFTING    → make_spear, build_shelter, weave_basket, make_fire
EXPLORATION → climb_tree (see farther), scout_area, mark_trail
SOCIAL      → signal, call_for_help, share_food (Phase 3)
```

### Effect Bounds

The oracle limits the effects of any innovated action:

```python
EFFECT_BOUNDS = {
    "hunger": (-30, 10),    # max -30 hunger (very good food), max +10
    "energy": (-20, 20),    # max -20 (very tired), max +20 (very rested)
    "life": (-15, 10),      # max -15 damage, max +10 healing
}

def clamp_effects(effects: dict) -> dict:
    for key, (min_val, max_val) in EFFECT_BOUNDS.items():
        if key in effects:
            effects[key] = max(min_val, min(max_val, effects[key]))
    return effects
```

## Phase 2 — Crafting & Prerequisites

### Inventory

For innovations like "build_shelter" to work, agents need inventory:

```python
class Inventory:
    items: dict[str, int]  # {"wood": 3, "stone": 1, "fruit": 2}
    max_slots: int = 10
    
    def add(self, item: str, qty: int): ...
    def remove(self, item: str, qty: int): ...
    def has(self, item: str, qty: int) -> bool: ...
```

### Recipes as precedents

When an agent innovates something that requires materials, the oracle records the "recipe":

```python
# Precedent for "build_shelter":
{
    "action": "build_shelter",
    "requires_items": {"wood": 5},
    "requires_tile": ["forest", "land"],
    "effects": {"energy": -15},
    "world_effect": "creates shelter at (x,y)",  # new: effects on the world
    "time_cost": 3  # ticks it takes (future)
}
```

## Considerations for Claude Code

- Innovation is the hardest feature to test because it depends on the LLM. Create tests with LLM mocks.
- Maintain a list of "expected" innovations in tests: if an agent invents "fly" and the oracle approves it, the test fails.
- Balance is critical: if innovating is too easy, agents invent everything in 10 ticks. If it's too hard, they never innovate.
- Special logging for innovations: each new innovation should be a highlighted event in the logs.
