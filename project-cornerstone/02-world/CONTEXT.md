# 02 — World System

## Current State (Phase 0)

The world is a 50x50 2D tile matrix randomly generated with three types:
- **water** (15%): intransitable
- **land** (65%): transitable, sin recursos
- **tree** (20%): transitable, contiene fruta (1-5 unidades)

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

### Day/night cycle
```python
# Every 24 ticks = 1 day
# Ticks 0-15: day (normal)
# Ticks 16-20: sunset (reduced vision: radius - 1)
# Ticks 21-23: night (vision radius - 2, energy spent 50% more)
DAY_LENGTH = 24
NIGHT_START = 16
DEEP_NIGHT_START = 21
```

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
