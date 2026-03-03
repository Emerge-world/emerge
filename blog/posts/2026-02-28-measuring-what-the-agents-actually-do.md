---
title: "Day 5: Measuring what the agents actually do"
date: 2026-02-28
tags: [audit, prompts, testing, phase-1]
pr: 5
---

I kept changing things and not knowing if they helped. I'd tweak a line in the agent prompt, run the simulation, watch the agents move around, and think: "that seems better?" But "seems better" is not a methodology. I needed a way to compare two runs and say something true about how behavior changed.

## What I built

An audit system. Two new modules: `audit_recorder.py` and `audit_compare.py`.

The recorder watches what agents do each tick — their decisions, stats, memory states — and writes structured JSONL files to an `audit/` folder inside each run's log directory. It also computes a SHA-256 hash of every prompt file at the start of the run, so you can always reconstruct exactly which prompts produced which behavior. All of this is opt-in via a `--audit` flag; there's no performance impact when you don't need it.

The comparison tool reads two audit directories and produces a report with four sections: a diff of the prompt hashes (what actually changed), a metrics table (survival rates, action counts, average stats), behavioral fingerprint bars (what fraction of actions were each type), and stat sparklines (life/hunger/energy trends over time). You run it after two sessions with different prompts and it tells you, in numbers, what changed.

I also added two new prompt templates for agents in critical states: `energy_low.txt` and `energy_critical.txt`. When an agent's energy drops below a threshold, their prompt shifts — the language around their condition becomes more urgent. This matters because the same objective information ("energy: 15") means different things to an agent who has been gradually depleting versus one who just sprinted across the map. Framing changes behavior.

And the context files got their names cleaned up — from `CONTEXT.md` to `*_context.md` — which is a small thing, but it makes them easier to reference and less likely to collide with other `CONTEXT.md` files floating around.

## Why it matters

This is the infrastructure that makes everything else defensible. Without it, prompt iteration is folklore — you iterate, you form impressions, you commit changes based on vibes. With it, you can run a controlled comparison: same seed, same world, same agents, different prompts. The question "did this change improve agent behavior?" becomes answerable.

The prompt SHA hashes are a small detail with outsized impact. Six months from now, when you're looking at a run log and wondering what version of the system produced it, the hash tells you exactly which prompts were active. Reproducibility as a first-class property.

## Things to consider

The metrics the audit captures are behavioral proxies, not ground truth. "Survival rate" tells you something about whether the prompts produce agents that stay alive, but it doesn't tell you whether the agents are making *good decisions* — just lucky ones, or ones that exploit some consistent feature of the world generation. An agent who always walks to the nearest tree and eats will survive, but isn't interesting.

There's also a risk that the audit system becomes the optimization target. If you tune prompts to maximize "survival rate" and "action diversity," you might end up with agents that score well on the metrics while becoming less human-like in their reasoning. The audit is a tool for detecting regressions, not a fitness function.

## What's next

Having the comparison tool is one thing. Using it systematically is another. The value compounds when you start every prompt change with a hypothesis, run the comparison, and record the result. That workflow doesn't happen automatically — it requires discipline to follow consistently. Eventually it might make sense to codify it: "you're not allowed to merge a prompt change without a before/after audit run." Not now, but soon.
