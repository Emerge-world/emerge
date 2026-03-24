# 02 — World System

## Current State (Phase 2)

The world is a configurable 2D tile matrix (default 15×15, overridable via `--width`/`--height` CLI flags) generated with Perlin noise via the `opensimplex` library. Eight tile types are implemented:

| Tile     | Walkable | Resources          | Passive effect                                        |
|----------|----------|--------------------|-------------------------------------------------------|
| water    | No       | —                  | Impassable                                            |
| sand     | Yes      | —                  | —                                                     |
| land     | Yes      | —                  | —                                                     |
| tree     | Yes      | fruit (1–5)        | —                                                     |
| forest   | Yes      | mushroom (1–3)     | —                                                     |
| mountain | Yes      | stone (2–5)        | +6 energy cost to enter                               |
| cave     | Yes      | stone (1–4)        | +20 energy when resting inside                        |
| river    | Yes      | water (qty=99, ∞)  | Oracle-determined life damage + +3 energy cost to enter |

**Generation:** Two-pass Perlin noise. Primary heightmap assigns biomes; secondary river-noise map carves channels through sand/land zones.

**Height thresholds** (in `config.py`):
```
h < WORLD_HEIGHT_WATER    (0.28) → water
h < WORLD_HEIGHT_SAND     (0.38) → sand  (or river if river noise < WORLD_RIVER_THRESHOLD)
h < WORLD_HEIGHT_LAND     (0.70) → land  (or river if river noise < WORLD_RIVER_THRESHOLD)
h < WORLD_HEIGHT_TREE     (0.76) → tree
h < WORLD_HEIGHT_FOREST   (0.82) → forest
h < WORLD_HEIGHT_MOUNTAIN (0.90) → mountain
h < WORLD_HEIGHT_CAVE     (0.96) → cave
else                              → mountain peak (TILE_MOUNTAIN)
```

**Resource regeneration:**
- Trees (fruit): dawn regen, 30% chance per depleted tree tile
- Forests (mushrooms): dawn regen, 30% chance per depleted forest tile
- Mountain / cave (stone): no regen — finite resource
- River (water): quantity=99, inexhaustible (`consume_resource()` short-circuits for `type="water"`)

**New resources require innovation:** `mushroom`, `stone`, and `water` are not accessible via base actions. Only `fruit` works with `eat`. Agents must innovate `forage`, `mine`, `drink`, etc. — preserving the emergence-first philosophy.

### Known Issues

1. **Fresh runs regenerate from seed**: Starting a new simulation rebuilds the world from config + seed rather than loading a prior `world_state.json` snapshot.
2. **Snapshots are export-only**: `SimulationEngine.save_world_state()` can write `world_state.json`, but there is no first-class loader that restores a run back into `World`.

## Phase 1 — Quick wins

### ✅ Generation with Perlin Noise (implemented — see DEC-016)
Replaced white-noise generation with two-pass Perlin noise (`opensimplex`) producing coherent biomes (sand beaches, plains, forests, mountains, caves, rivers).

### ✅ Resource regeneration (implemented — see DEC-015)
```python
# At dawn (tick % DAY_LENGTH == 0, skip tick 0):
# - Depleted tree tiles: 30% chance to regrow 1–3 fruit
# - Depleted forest tiles: 30% chance to regrow 1–3 mushrooms
RESOURCE_REGEN_CHANCE = 0.3
RESOURCE_REGEN_AMOUNT_MIN = 1
RESOURCE_REGEN_AMOUNT_MAX = 3
```

### World snapshots and replay gap
- `uv run main.py --save-state ...` writes a `world_state.json` snapshot at the end of the run.
- That snapshot is currently an export artifact for inspection, not the canonical replay source.
- Canonical run reconstruction is intended to come from `data/runs/<run_id>/events.jsonl`; a world-state loader is not implemented yet.

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

### Resource Regeneration (DEC-015)

At each dawn (`tick % DAY_LENGTH == 0`, skipping tick 0), each depleted tree tile
rolls for fruit regeneration:

- **Trigger:** Dawn (every 24 ticks, starting tick 24)
- **Eligibility:** Only tree tiles with no active resource entry (depleted trees)
- **Probability:** `RESOURCE_REGEN_CHANCE = 0.3` (30% per eligible tree)
- **Quantity:** `random.randint(RESOURCE_REGEN_AMOUNT_MIN, RESOURCE_REGEN_AMOUNT_MAX)` → 1–3 fruit
- **Determinism:** Uses `World._rng = random.Random(seed)`, a dedicated instance
  separate from the global `random` module used during world generation.
- **Implementation:** `World.update_resources(tick)` called from `SimulationEngine._run_tick`

---

## Phase 2 — Survival Depth

### New tiles ✅ (implemented — see DEC-016)
| Tile     | Walkable | Resources              | Notes                                          |
|----------|----------|------------------------|------------------------------------------------|
| water    | No       | —                      | Impassable deep water                          |
| sand     | Yes      | none                   | Water-land transition                          |
| land     | Yes      | none                   | Base tile                                      |
| tree     | Yes      | fruit (1–5)            | Dawn regen 30%                                 |
| forest   | Yes      | mushroom (1–3)         | Dawn regen 30%; requires forage innovation     |
| mountain | Yes      | stone (2–5)            | +6 energy to enter; requires mine innovation   |
| cave     | Yes      | stone (1–4)            | +20 energy rest bonus; requires mine innovation|
| river    | Yes      | water (∞)              | Oracle-determined life damage; requires drink  |

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

- The current `World` class is still monolithic. If world logic keeps growing, split it into `Grid`, `ResourceManager`, and `WeatherSystem`.
- World tests must verify: deterministic generation with seed, walkability, resource consumption, regeneration.
- The world JSON must be backwards compatible: new fields are optional.
