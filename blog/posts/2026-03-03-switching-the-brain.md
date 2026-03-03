---
title: "Day 10: Switching the brain"
date: 2026-03-03
tags: [llm, qwen, model-upgrade, phase-1]
pr: 10
---

The model had been showing its limits for a while. Responses that were structurally correct but semantically thin. Action choices that looked reasonable from the outside but revealed, on closer reading, that the agent wasn't really engaging with its memory or its situation — it was pattern-matching to whatever the training data suggested. And occasionally, JSON that was almost right but broken in ways that the parsing layers had to paper over.

I found Qwen 3.5. It was better.

## What I built

A model upgrade, plus some plumbing that had been accumulating debt.

The model string in the config changed from `qwen2.5:3b` to `qwen3.5:9b` (tuned back to `:4b` in a follow-up pass after testing). The LLM client got improvements: better logging of what goes in and what comes out, cleaner response processing, and more robust handling of the cases where the model returns something unexpected. The agent got a small improvement to how it formats its context before sending it to the LLM.

This is a small PR in terms of line count, but it touches the most central piece of the whole system.

## Why it matters

Everything in Emerge depends on the quality of the LLM's reasoning. The oracle, the memory compression, the innovation validation, the action decisions — all of it bottoms out at "what does the model do with this prompt?" A model that reasons more carefully about the world description produces agents that feel more alive. A model that pattern-matches produces agents that feel mechanical.

Qwen 3.5 is better on the things that matter here: structured JSON output, contextual reasoning over a few hundred tokens of world state, and following instruction hierarchies in the system prompt. It's not a step-change — it's still a small model running locally — but it shifts the ceiling on what's possible before you hit model limitations.

The logging improvements are less glamorous but arguably more valuable in the long run. When something goes wrong with the LLM — and it will, it always does — the logs need to tell you exactly what was sent, what came back, and what the parser made of it. That's debugging infrastructure, and debugging infrastructure pays for itself.

## Things to consider

The model version is now `qwen3.5:4b` after the initial `9b` proved too slow for interactive sessions with multiple agents. That's the first time the simulation's design has bumped up against hardware constraints in a visible way. As the system gets more complex — more agents, more memory, more oracle calls — the question of which model to run locally will come up again. The config makes it easy to switch, but the right answer isn't static: it depends on how fast the machine is, how many agents you're running, and what you're willing to trade off between reasoning quality and tick speed.

There's also something worth being aware of: switching models changes the "character" of the agents subtly. The same prompts produce slightly different reasoning styles. Precedents cached by the old model might represent judgments the new model would have made differently. The audit system could in principle detect this — a run with qwen3.5 should have a different behavioral fingerprint than a run with qwen2.5 — but nobody ran that comparison explicitly.

## What's next

The model upgrade unlocks better reasoning, but the prompts were written for the old model. There's probably some version of prompt optimization — tuned specifically for qwen3.5's particular strengths and weaknesses — that would yield noticeably better agent behavior. That kind of prompt tuning needs the audit system to be systematic, and it's one of the items on the Phase 1 list that hasn't been touched yet.

The deeper question is how long this model stays current. The landscape of locally-runnable LLMs is moving quickly. Qwen 3.5 is good today; in six months there will be something better. The abstraction is clean — one config string controls the model — but it's worth thinking about what "upgrade path" looks like as the simulation gets more complex and the benchmark for "good enough reasoning" rises.
