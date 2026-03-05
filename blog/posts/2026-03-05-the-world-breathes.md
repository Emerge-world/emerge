---
title: "Day 13: The world breathes"
date: 2026-03-05
tags: [world, resources, phase-2]
pr: 13
---

There was a ceiling I kept running into. Run the simulation with three agents and a fixed seed, let it go for thirty ticks, and the fruit is gone. Every tree stripped. The agents mill around, still alive, still deciding — but there is nothing left to eat. The world had become a closed system, and closed systems run down. I could test short runs fine, but anything longer than half a day was a slow-motion ruin. I needed the world to renew itself.

## What I built

At every dawn — the moment when `tick % 24 == 0`, starting from tick 24 — each depleted tree rolls a 30% chance to regrow. If it wins the roll, it comes back with one to three fruit. Trees that still have fruit are left alone. The whole pass runs in a single method, `update_resources`, called by the engine at the end of each tick after the agent loop has finished.

The trickier part was making it deterministic. The rest of the simulation uses Python's global `random` module seeded at startup, which means the sequence of random calls is tied to everything else that happens in a run — how many agents act, in what order, what they decide. If I used that same global state for regeneration, the fruit pattern would shift every time agent behavior changed, which would make debugging nearly impossible. Instead, the world gets its own `random.Random` instance, seeded separately from the world seed, isolated from everything else. The regen sequence is now a pure function of the world seed and the tick — no matter what the agents do, the same trees regrow on the same dawns.

Eleven tests cover it: dawn detection (only fires when expected, not at tick zero), correctness (depleted trees regrow, full trees don't), determinism (run twice with seed 42, get identical results), and edge cases around empty worlds and skipped ticks.

## Why it matters

The immediate problem is practical: without regeneration, fruit is finite, and the simulation has a hard ceiling around tick 30 for any multi-agent run. That makes it impossible to test anything that takes time to develop — inventory accumulation, crafting chains, agents learning to plan ahead. The world needs to stay alive for those features to mean anything.

But there is something more interesting underneath the practicality. The simulation is now a world that operates on cycles. Dawn arrives, trees come back, the agents wake up to a slightly different landscape than the one they left. The world has a rhythm. That rhythm is completely invisible to the agents right now — they don't know what dawn means, they don't plan around it, they don't wait for it — but it exists in the substrate, ready to matter once the agents develop any kind of temporal awareness.

## Things to consider

The constants are guesses. A 30% chance and one to three fruit felt reasonable, but I haven't actually run the simulation long enough with these values to know if they create a sustainable equilibrium. Too generous and agents never feel pressure; too stingy and the world still starves eventually, just more slowly. The right values depend on how many agents are running, how aggressively they eat, and what other food sources might exist in later phases. This is something to revisit once inventory and crafting are in.

There is also a subtlety in the isolation: the dedicated RNG is seeded from the world seed, not from an independent source. That means two worlds with different seeds will have different regen patterns, which is what you want — world 42 and world 99 should feel different. But it also means that if I ever change what else uses the world seed during generation, the regen sequence stays stable. The isolation is one-directional by design.

One edge I noticed while writing tests: the method returns the list of positions where regeneration fired. The engine logs the count, but the positions themselves are thrown away. That return value might be useful later — for events, for agent perception, for the oracle to notice that a previously empty tile now has fruit. For now it's a breadcrumb.

## What's next

Personality is the last item on the Phase 1 list. I want agents to have character — a curiosity score that makes one more likely to experiment, a caution that makes another prefer familiar actions when resources are low. The prompts are the right place to express this: not as hard rules, but as a framing that colors how the agent sees its situation. A curious agent would notice the unexplored corner of the grid; a cautious one would notice its falling energy.

After that, Phase 2 opens up properly. Inventory is next — agents that can carry things, which means actions with lasting consequences beyond the current tick. Crafting follows from inventory. And with regeneration already in place, the world can sustain those longer, more deliberate runs. The ceiling is gone.
