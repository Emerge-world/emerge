---
title: "Day 14: The ground beneath their feet"
date: 2026-03-05
tags: [world, terrain, phase-2]
pr: 14
---

The world was flat in a way that bothered me more the longer I looked at it. Not visually — the grid had water, land, and trees — but experientially. An agent moving through what would be a dense forest was having the same experience as one crossing what should be a sandy beach or scaling a rocky peak. The coordinate changed; nothing else did. Every tile was neutral. I wanted the ground to matter.

## What I built

The first thing I replaced was how the world is generated. The old approach was pure white noise — each tile was assigned randomly, which produced a scattered, incoherent landscape. Now the world uses Perlin noise: a height field that determines elevation, plus a secondary field that carves rivers through the terrain. The result is something that feels like geography. Sand clusters near the edges. Forests fill the mid-elevation zones. Mountains rise toward the center. Caves appear in rocky terrain, and rivers cut across the map in continuous bands.

That gave us five new tile types on top of the existing ones: sand, forest, mountain, cave, and river. But a new tile is only meaningful if it does something. Sand is safe but sparse. Forests are rich with mushrooms. Mountains are dangerous — the oracle now applies tile-specific costs when an agent moves into high-risk terrain, assessing the environment and determining how much that crossing should cost. Rivers deal actual damage on entry. And caves — caves are the most interesting — they provide shelter. An agent who rests in a cave recovers meaningfully more energy than one who rests on open ground. The world now has a best place to sleep.

I also wired up resources to terrain: different tile types spawn different materials, and the configuration drives it entirely. That's what makes the new `--width` and `--height` CLI flags feel like more than a convenience — you can now generate fundamentally different worlds with different seeds and dimensions, each with its own geography and resource distribution.

## Why it matters

The simulation gains its first layer of genuine environmental pressure. Before this, the relevant question was "is there food nearby?" Now the relevant question is also "what kind of ground am I standing on, and what will it cost me to move through it?" That's not complexity for its own sake — it's the substrate for strategy. A cautious agent should prefer to cross sand rather than a river. An agent with low energy should seek a cave before trying to rest in the open. None of that behavior is programmed; it just becomes rational given the new landscape.

More practically: resources are now tied to terrain. Mushrooms grow in forests. Stone appears near mountains. That means what an agent can pick up depends on where they are — and where they are has consequences. The connection between terrain, resources, and survival is starting to close into a loop.

## Things to consider

The oracle currently asks the LLM to estimate how much damage a tile crossing should inflict. That's more expensive and less deterministic than a hardcoded lookup, and it creates a soft dependency on model reasoning for what should be a physics fact. There's a config dict for tile risks already — the oracle could use it directly and bypass the LLM entirely for this calculation. The current design is expressive but probably overkill for something as simple as "rivers hurt, mountains cost energy."

There's also the question of agent awareness. Right now, agents can see the tile types in their grid view, but they don't have a vocabulary for what those tiles mean to their survival. They'll learn indirectly — take damage, avoid the tile — but that learning is implicit and slow. Once semantic memory is more developed, it might be worth making tile-damage part of what agents can articulate to themselves.

And then there's the save format. The world is generated from a seed at startup, which means the same seed always produces the same map — good for determinism. But if we ever want persistent worlds or map saving between sessions, the Perlin seed and all its parameters need to travel with the save state. That's not hard, but it's easy to forget until you need it.

## What's next

Inventory arrived in the next PR, and the connection is direct: now that terrain determines what resources exist where, agents can go to those places, pick up what's there, and carry it forward. The ground finally has consequences; the hand that reaches down and collects something from it is the next piece. After that, crafting — using what you've collected to build something that outlasts the tick. The loop from terrain to resource to inventory to tool is the spine of Phase 2, and this PR laid the first bone.
