---
title: "Day 12: The oracle remembers"
date: 2026-03-04
tags: [oracle, persistence, phase-1]
pr: 12
---

Every time I restarted the simulation, the oracle had to re-learn everything from scratch. It already knew how to reason — it could consult the LLM to decide that water blocks movement, that eating fruit is always physically possible, that this particular agent's innovation of "fishing" makes sense for a water tile. But none of that carried forward. The moment the process ended, all that accumulated judgment was gone. The next run started with a blank slate, the same questions asked again, the same LLM calls made. It felt wrong in a way that was hard to articulate at first — not a bug, exactly, but a kind of structural amnesia.

## What I built

The oracle now saves everything it has learned to a small JSON file when a run ends, and reloads it automatically when a new run starts. The file lives at `data/precedents_{seed}.json` — one file per world seed, so different world configurations don't bleed into each other. The schema is minimal: a version number, the seed, the tick when it was saved, and the full precedent dictionary. Nothing more.

The save happens in a `finally` block, which means it fires even if the simulation crashes mid-run. And the save itself never raises — if it hits a disk error or can't serialize something, it logs a warning and moves on quietly. I didn't want a bookkeeping failure to corrupt a simulation run or hide a more interesting exception.

Loading is equally defensive: if the file doesn't exist, nothing happens. If the JSON is corrupt, existing precedents are left untouched and a warning is logged. The simulation always has somewhere to fall back to.

## Why it matters

The oracle was already implementing a kind of institutional memory within a run — every physics judgment, every validated innovation, every action outcome cached so it never had to re-ask the same question. That's what makes it deterministic. What was missing was any continuity across the restart boundary.

Now the world accumulates knowledge. After a few runs with the same seed, the oracle already knows that land is traversable, that trees are traversable, that eating fruit is possible. It knows what fishing does on a water tile if a previous run established that. The LLM is consulted only for genuinely novel situations — the first time an agent tries something in a particular context. After that, it's free. This matters not just for performance, but for the character of the simulation: the world is starting to have a history that outlasts any individual run.

## Things to consider

Precedents are saved with a version number and a seed, but they're not versioned against the oracle's *logic*. If I change how the oracle judges traversability — say, making forests cost more energy to enter instead of blocking movement entirely — old precedents will silently contradict the new rules. A run with an existing precedents file would behave differently from a fresh run. That inconsistency is invisible.

There's also a stranger question hiding here: what does it mean for the oracle to remember innovations that no current agent knows? A precedent file might contain a cached outcome for "fishing" established by Ada in a previous run. In this run, no agent has discovered fishing yet. The precedent exists, waiting. When an agent eventually invents fishing, the oracle will immediately know what it does — no LLM call needed. Is that contamination? Or is it just the world having physics? I'm not sure.

And then there's the key format itself. Right now, precedent keys are hand-written strings like `"custom_action:fish:tile:water"`. They're fragile — two semantically identical situations might produce different strings if formatted slightly differently. The structured dataclass approach (`PrecedentKey` with fields for action, tile type, tool presence) has been deferred as unnecessary for now. But every precedent saved to disk makes that technical debt a little more concrete. At some point, the file format is load-bearing and changes become migrations.

## What's next

Personality traits are the last remaining Phase 1 item. I want agents to have something like character — a curiosity that makes one agent more likely to try new things, a caution that makes another prefer to rest when energy drops. With persistent precedents and dual memory already in place, personality starts to feel achievable: not as a separate system, but as a bias woven into the existing prompts. A curious agent might frame its decisions differently, see the same world and be drawn toward the unexplored corner of it.

Beyond that, Phase 2 is getting close. Weather, resource regeneration, inventory, crafting. Precedents become much more interesting when the world is more complex — when an agent can fish with a tool versus bare-handed, and the oracle needs to distinguish those two situations. The groundwork laid here makes that distinction straightforward to add: expand the key, migrate the file format. The simulation is starting to feel like something that could run for a long time and accumulate something real.
