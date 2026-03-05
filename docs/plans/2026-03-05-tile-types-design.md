# Design: New Tile Types + Perlin Noise World Generation

**Date:** 2026-03-05
**Phase:** 2 — Survival Depth
**Status:** Implemented

## Problem

The world uses white-noise tile generation and only has 3 tile types (water, land, tree), producing an incoherent map with no geographic structure and only one resource (fruit).

## Solution

Add 5 new tile types with coherent Perlin-noise generation, new resources, and tile-specific passive effects.

## Tile Properties

| Tile     | Walkable | Passive effect                   | Resource     |
|----------|----------|----------------------------------|--------------|
| water    | No       | —                                | —            |
| sand     | Yes      | —                                | —            |
| land     | Yes      | —                                | —            |
| tree     | Yes      | —                                | fruit (1–5)  |
| forest   | Yes      | —                                | mushroom (1–3) |
| mountain | Yes      | +6 energy cost to move through   | stone (2–5)  |
| cave     | Yes      | +20 energy when resting inside   | stone (1–4)  |
| river    | Yes      | +3 energy cost (hardcoded) + Oracle-determined life damage | water (∞)    |

## Key Decisions

- **All tiles walkable**: Even rivers. Risk is emergent (Oracle/LLM judges river strength on first crossing, cached as precedent).
- **Mountain**: Hardcoded extra energy cost (TILE_RISKS), not LLM-determined.
- **Cave shelter**: Passive rest bonus (+20 energy) via TILE_REST_BONUS config.
- **New resources require innovation**: mushroom, stone, water are inaccessible via base actions — agents must innovate "forage", "mine", "drink" etc. Only `fruit` works with the base `eat` action.
- **World size via CLI**: `--width` and `--height` flags added to main.py.

## Generation Algorithm

Perlin noise (opensimplex library) with two passes:
1. Primary heightmap → assigns biome per tile based on height thresholds
2. River noise map → carves river channels through sand/land zones

Height thresholds (configurable in config.py):
```
h < 0.28     → water
0.28–0.38    → sand (or river if river noise < 0.15)
0.38–0.70    → land (or river if river noise < 0.15)
0.70–0.82    → forest
0.82–0.90    → mountain
0.90–0.96    → cave
>0.96        → mountain peak
```

## Resource Regeneration

- Trees (fruit): existing dawn regen, 30% chance per depleted tree
- Forest (mushroom): same dawn regen logic added for forests
- Mountain/cave (stone): finite, no regeneration
- River (water): always quantity=99, never depleted
