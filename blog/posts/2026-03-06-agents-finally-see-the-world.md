---
title: "Day 18: The Map That Lied"
date: 2026-03-06
tags: [prompts, world, agent-perception, phase-2]
pr: 18
---

I had been staring at the agent logs for a while, watching agents stand in caves and forests and riverbeds and make decisions as if they were all just... ground. The world had eight distinct biomes. The agents had no idea. I'd given them eyes that could only see three things.

## What I built

The ASCII grid that agents use to perceive their surroundings had a quiet bug. When the Perlin noise world generator landed in an earlier PR, it brought five new tile types — sand, forest, mountain, cave, river — alongside the existing land, water, and tree tiles. But the renderer that turned those tiles into characters for the agent's prompt only knew how to handle three of them. Everything else collapsed silently to a dot. From the agent's perspective, standing in a mountain cave or on a riverbank looked identical to standing in a featureless field.

The fix was a dispatch table at the module level: each tile type maps to a function that returns the right character. Forests became `f`, mountains `M`, caves `C`, rivers `~`, sand `S`. The old chain of if/elif branches disappeared. More importantly, the agent's decision prompt now includes a `[Tile: cave]` annotation every single tick — so when an agent is standing in a cave, they know it, and when they write an innovation that requires cave terrain, the system can validate that requirement against something real.

The oracle prompts got the same treatment. Effect guidelines for custom actions were calibrated with explicit labor tiers — light foraging costs 3–8 energy, heavy mining costs 15–20 — so the oracle's rulings on custom actions have consistent footing. Innovation validation now knows the full list of valid terrain types, which closes the loop between the world generator and the judgment layer.

## Why it matters

Emergence can't happen if the agents can't perceive the world they're supposed to be responding to. The whole premise of Emerge is that agents discover survival strategies through experience — foraging in forests, mining in mountains, seeking shelter in caves — but none of that is possible if the world renders as a uniform gray field. An agent standing next to a river who wants to innovate a `drink` action needed the oracle to know what `requires: {tile: river}` even meant. Now it does.

This PR is a fidelity layer. It doesn't change what agents can do — it changes how accurately the simulation communicates the world to them, and how accurately their intentions are validated against it. That accuracy is the substrate on which interesting behavior grows.

## Things to consider

There's a question hiding here about what agents can actually learn from the tile they're standing on. Right now `[Tile: cave]` is a bare label — it tells the agent where they are but nothing about what that means. Do caves shelter from weather? Do they harbour predators? Do they stay cooler in summer? An agent standing in a cave for the first time has no basis to expect anything other than what they already know. The expectation is that this knowledge emerges through experience — the agent rests in a cave, gets a bonus, remembers it, generalises. But the prompt injection gives them the vocabulary without the grammar. Is that enough scaffolding, or does it inadvertently lead them to over-index on terrain labels they don't yet understand?

There's also a subtle tension in how oracle effect guidelines and agent perception interact. The calibrated energy tiers in the oracle prompts (`-3 to -8` for light labor, `-15 to -20` for heavy) are a human judgment about what's reasonable. But the oracle is supposed to be the neutral arbiter of world physics. As more tile types introduce more exotic innovations — mining with custom tools, channeling river water — the effect guidelines will need to evolve. Who owns that calibration, and how does it stay consistent as the action space grows?

## What's next

Giving agents terrain awareness opens up a space that wasn't really accessible before. An agent who knows they're standing on a riverbank can now propose innovations that genuinely require water — fishing, drinking, damming — and the oracle can reason about those proposals against the actual world. The innovation system was designed for this kind of terrain-grounded creativity, but it was somewhat theoretical until now.

What becomes imaginable next is a world where terrain shapes culture. Agents who live near rivers develop water-related skills. Cave-dwellers learn to rest efficiently. Mountain agents invest in mining. These aren't behaviours I'm going to script — but they're behaviours that, given accurate perception, the system could develop on its own. That's the bet.
