---
title: "Day 4: Getting the prompts out of the code"
date: 2026-02-28
tags: [prompts, oracle, architecture, phase-1]
pr: 4
---

There's a moment in every project like this where you realize the thing you thought was configuration is actually code, and the thing you thought was code is actually policy. The agent prompts were policy — they described how agents should think about the world. But they lived inside Python classes, wrapped in f-strings, halfway up a 200-line file. To change one word, you had to touch the simulation logic.

That couldn't last.

## What I built

Three things came together in this PR. First, the knowledge base got renamed from `project-bible` to `project-cornerstone` — a small rename, but it mattered. "Bible" implied something fixed and handed down. "Cornerstone" felt more honest: the foundation you build on, not the scripture you follow.

Second, and more substantially: the agent prompts moved out of Python and into text files. A new `prompts/` directory holds all the prompt templates, organized by module. A small `prompt_loader.py` reads them with variable substitution using Python's built-in `string.Template`. No new dependencies, no Jinja2, no complexity — just text files that can be edited without opening a Python interpreter.

Third, the oracle got a rethink. Before this, it was checking a list of hardcoded rules before consulting its LLM — "is this a valid direction? is this tile walkable?" But that's backwards. The oracle is supposed to embody world physics through reasoning, not through a rulebook. Now all actions route through a physical reflection step: the oracle's LLM reasons about plausibility once for each novel situation, caches the result as a precedent, and uses that precedent forever after. It also means movement now supports all 8 compass directions, which the old hardcoded rules didn't bother to handle.

## Why it matters

If the prompts are configuration, they need to be configurable. Every iteration on how agents think — every tweak to their personality, their sense of urgency, their understanding of the world — should be a one-line edit in a text file. That's the difference between something you experiment on and something you maintain.

The oracle change is deeper. An oracle that hardcodes physical rules is just a validator with extra steps. An oracle that *reasons* about physics and remembers its conclusions is a different kind of thing — one that can be surprised, one that can be wrong in interesting ways, one that can be evolved. The precedent system means the reasoning cost is paid once and amortized forever.

## Things to consider

Prompt files are easy to edit. Maybe too easy. When the logic of how an agent makes decisions is in a text file, it's one accidental keystroke away from a subtle behavior change that no test will catch. The audit system doesn't exist yet at this point — there's no way to compare "before" and "after" on agent behavior in any principled way.

There's also something worth noting about the oracle precedent system: it only captures the oracle's first encounter with a situation. If the first encounter was an edge case — an agent with unusual stats, or a weird tile configuration — the precedent might be subtly wrong for typical cases. Precedents are efficient, but they can also bake in early mistakes.

## What's next

Having prompts in files is table stakes. The real payoff comes when you can swap them programmatically, run two versions in parallel, and actually measure which produces better agent behavior. That measurement layer doesn't exist yet. Building it is the natural next step — and it would change how every future prompt change gets evaluated.
