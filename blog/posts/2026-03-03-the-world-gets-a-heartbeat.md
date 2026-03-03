---
title: "Day 9: The world gets a heartbeat"
date: 2026-03-03
tags: [day-night, world, survival, phase-1]
pr: 9
---

The world felt frozen. Not wrong, exactly — agents moved, ate, rested — but all of it happened in an undifferentiated brightness. It was always noon. The ticks counted up but they didn't mean anything beyond "another step." I kept thinking: real survival is shaped by time. When to rest. When to push through. When the dark makes everything harder.

I wanted the world to have a heartbeat.

## What I built

A day/night cycle. One tick equals one in-world hour. Twenty-four ticks make a full day, split into three periods: daytime runs from hours 0 to 15 — full vision, normal energy costs, the world as you'd expect it. Sunset covers hours 16 to 20 — vision shrinks by one tile. Night runs from hours 21 to 23 — vision drops by two tiles, and every action that costs energy costs half again as much.

The whole system lives in a new `simulation/day_cycle.py` module with a `DayCycle` class. It handles everything about time: which period it is, what the vision radius should be, what multiplier to apply to energy costs. The engine computes the current vision radius each tick and passes it to the world; the oracle uses the multiplier when it resolves actions. Each piece of the system only knows what it needs to know.

The start hour is configurable — you can launch the simulation at dawn, midday, or midnight. `WORLD_START_HOUR = 6` in the config, or `--start-hour` on the command line. The time description gets injected into the agent's decision prompt, so agents actually know whether it's day or night when they're choosing what to do.

Rest is intentionally not penalized at night. Resting at night should feel like the right choice, not a forced one.

## Why it matters

Time is the most basic structure in survival. Animals don't eat at the same rate at 3am and 3pm. Energy has a different meaning when you're about to run out of daylight. The day/night cycle isn't just flavor — it's a new dimension of constraint that agents need to reason about, and reasoning about constraints is where interesting behavior comes from.

It also sets the semantic grounding for everything that follows. "One tick equals one hour" means resource regeneration can happen at dawn, weather patterns can follow daily cycles, and eventually sleep might become a real mechanic rather than just "resting when energy is low." Phase 2 resource regeneration is already easier to design now that ticks have meaning.

## Things to consider

Agents know what time it is — it's in their prompt. But do they *act* on it? There's a difference between "the agent is told it's night" and "the agent's strategy shifts because it's night." If the LLM treats the time description as background noise, the day/night cycle becomes cosmetic rather than mechanical. The audit system could help answer this, but it would require designing behavioral metrics specifically for temporal reasoning.

There's also an asymmetry in the design: night makes things harder, but there's no reward for enduring it. An agent who successfully navigates to food in low visibility and high energy cost gets nothing extra for the difficulty. That might be fine — the reward is surviving — but it means there's no incentive to develop specifically nocturnal strategies. Everything optimal at night is just "survive until daytime."

The 1.5x energy multiplier is a number I chose. It feels right, but it's entirely untested. Too low and night is just noise. Too high and every agent should sleep through it, which is rational but makes the simulation less interesting. That number probably needs tuning once there's data.

## What's next

The world now has time. The obvious next question is whether it has seasons, or weather, or any other time-varying structure beyond the daily cycle. Those are Phase 2 features, but the day/night system establishes the pattern for adding them: a dedicated module, a clean interface, injected into both the world mechanics and the agent prompt.

More immediately: what do agents do with night time? Do they start clustering near known food sources before dark? Do they rest preemptively, building up energy before the night multiplier kicks in? These would be signs of genuine temporal reasoning — and they'd be visible in the audit logs if you knew what to look for.
