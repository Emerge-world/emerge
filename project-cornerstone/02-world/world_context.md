# 02 — World System

## Current State (Phase 0)

The world is a 10x10 2D tile matrix randomly generated with three types:
- **water** (~15%): impassable — controlled by `WATER_RATIO = 0.15` in `config.py`
- **land** (~76.5%): passable, no resources — remaining tiles after water and trees
- **tree** (~8.5%): passable, contains fruit (1–5 units) — `TREE_DENSITY = 0.10` of land tiles

> **Note**: Previous docs listed 65% land and 20% trees, which was a planning target. The actual config values are `WATER_RATIO=0.15` and `TREE_DENSITY=0.10` (10% of land tiles), yielding ~8.5% trees overall.

### Known Issues

1. **Generation is white noise**: There's no geographic coherence. Water appears as scattered pixels instead of lakes/rivers. Trees don't form forests.
2. **Resources don't regenerate**: Once all fruit is eaten, the world is depleted.
3. **No resource variety**: Only fruit.
4. **No persistence**: The world regenerates every execution.

## Phase 1 — Quick wins

### Generation with Perlin Noise
Replace random generation with Perlin noise to create coherent biomes.

```python
# Proposed algorithm:
# 1. Generate heightmap with Perlin noise
# 2. height < 0.3 → water
# 3. height 0.3-0.4 → beach/sand (new tile)
# 4. height 0.4-0.7 → land (plains)
# 5. height 0.7-0.85 → forest (trees)
# 6. height > 0.85 → mountain (new tile, impassable but mineable)
# Library: `noise` (pip install noise)
```

### Resource regeneration
```python
# Every N ticks, trees without fruit have a probability to regenerate.
# Proposal: every 10 ticks, 30% chance per depleted tree to give 1-3 fruits.
RESOURCE_REGEN_INTERVAL = 10
RESOURCE_REGEN_CHANCE = 0.3
RESOURCE_REGEN_AMOUNT = (1, 3)
```

### World persistence
- Save the world as JSON when generating it.
- Ability to load a world from JSON to reproduce simulations.
- Format: `data/worlds/world_{seed}_{timestamp}.json`

## Implemented in Phase 1/2 (Day/Night Cycle)

### Day/Night cycle *(implemented — see DEC-010)*

1 tick = 1 in-world hour. The simulation starts at a configurable hour (default 06:00).

**Periods and effects:**

| Period  | Hours   | Vision radius | Energy cost multiplier |
|---------|---------|---------------|------------------------|
| Day     | 00–15   | 3 tiles       | ×1.0 (normal)          |
| Sunset  | 16–20   | 2 tiles       | ×1.0                   |
| Night   | 21–23   | 1 tile        | ×1.5 (move & eat only) |

**Constants (`simulation/config.py`):**
```python
DAY_LENGTH = 24               # ticks per in-world day
WORLD_START_HOUR = 6          # configurable via --start-hour CLI flag
SUNSET_START_HOUR = 16
NIGHT_START_HOUR = 21
NIGHT_VISION_REDUCTION = 2    # AGENT_VISION_RADIUS - this at night
SUNSET_VISION_REDUCTION = 1   # AGENT_VISION_RADIUS - this at sunset
NIGHT_ENERGY_MULTIPLIER = 1.5
```

**Code:** `simulation/day_cycle.py` — `DayCycle` class.
- `get_hour(tick)`: returns 0–23
- `get_day(tick)`: returns 1-indexed day number
- `get_period(tick)`: `"day"`, `"sunset"`, or `"night"`
- `get_vision_radius(tick)`: used by engine to fetch world tiles
- `get_energy_multiplier(tick)`: used by oracle to scale move/eat costs
- `get_prompt_line(tick)`: one-line time description injected into decision prompt

**Prompt integration:** `prompts/agent/decision.txt` includes `$time_info` as the first line.
Example: `TIME: Night (21:00, day 1). Vision severely reduced to 1 tile. Energy costs 50% higher.`

**Resource regeneration** tied to dawn: deferred to next PR.

---

## Phase 2 — Survival Depth

### New tiles
| Tile     | Walkable    | Resources              | Notes                          |
|----------|-------------|------------------------|--------------------------------|
| water    | No          | fish (future)          | Natural barrier                |
| sand     | Yes         | none                   | Water-land transition          |
| land     | Yes         | none                   | Base tile                      |
| tree     | Yes         | fruit, wood            | Wood = crafting resource       |
| forest   | Yes (slow)  | fruit, wood, mushrooms | Slows movement                 |
| mountain | No*         | stone, minerals        | *Walkable with innovation      |
| cave     | Yes         | shelter, minerals      | Protects from weather          |
| river    | No*         | drinking water, fish   | *Crossable with bridge         |

### Day/night cycle *(implemented — see "Implemented in Phase 1/2" above)*

### Weather system
```python
# Weather changes every 24-72 ticks
# Types: clear, rain, drought, storm
# Effects:
#   rain: resources regenerate 2x faster, energy spent 20% more
#   drought: resources don't regenerate, hunger rises 50% faster
#   storm: reduced vision, risk of damage (-5 life/tick if no shelter)
WEATHER_CHANGE_INTERVAL = (24, 72)
WEATHER_TYPES = ["clear", "rain", "drought", "storm"]
```

## Considerations for Claude Code

- The current `World` class is monolithic. Before Phase 2, split it into `Grid`, `ResourceManager`, `WeatherSystem`.
- World tests must verify: deterministic generation with seed, walkability, resource consumption, regeneration.
- The world JSON must be backwards compatible: new fields are optional.
