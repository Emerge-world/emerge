---
title: "Day 7: Agents that remember"
date: 2026-03-02
tags: [memory, agents, intelligence, phase-1]
pr: 7
---

Something was off, and I'd known it for a while. Agents were making decisions — real decisions, not random ones — but they weren't building on them. Every tick was a fresh start. An agent who learned at tick 5 that eating from trees near water was reliable would have forgotten it by tick 60. The same lesson would need to be learned again, and then forgotten again. They weren't experiencing the world. They were just reacting to it.

I wanted them to carry something forward.

## What I built

A dual memory system: episodic memory and semantic memory, living in a new `simulation/memory.py` module.

Episodic memory is the raw feed — up to 20 recent events, stored as strings. "I ate fruit and my hunger dropped." "I tried to move north but there was water." These are experiences, unprocessed, in the order they happened. The episodic feed is what an agent has just lived through.

Semantic memory is the distilled version — up to 30 compressed lessons, extracted from the episodic feed every 10 ticks by the LLM itself. The compression prompt asks: given these recent events, what are the generalizable lessons? What patterns are worth remembering beyond the specific moment? The results are things like "trees near water tend to have fruit" or "resting before long moves conserves energy across the board." Abstract, reusable knowledge.

The agent's decision prompt now shows both: a `[KNOW]` section for semantic memory and a `[RECENT]` section for episodic. The LLM sees what the agent has learned and what it just experienced, alongside the current world state. The compression adds one LLM call per agent every 10 ticks — a real cost, but one that compounds over time as agents accumulate knowledge rather than losing it.

Backward compatibility was worth taking seriously here: every site in the codebase that called `agent.memory` or `agent.add_memory()` kept working without changes, via a property shim.

## Why it matters

Memory is the precondition for identity. An agent without memory isn't really an agent — it's a stateless function that maps world state to action. Giving agents persistent, accumulating, structured memory is the step that makes it possible to say "this agent *knows* something." Not just "this agent has access to information."

The split between episodic and semantic matters more than it might seem. Episodic alone would just be a longer context window — recent events, more of them. Semantic memory is different in kind: it's the agent forming beliefs about the world, not just recording what happened. That's the thing that makes survival strategies possible, and eventually cultural transmission.

## Things to consider

The compression is done by the same LLM that makes agent decisions. That means the quality of semantic memory depends on the model's ability to generalize, which is uncertain for a 3B-parameter model. What if the model compresses in a biased way — consistently over-generalizing from lucky events, or failing to extract lessons from unlucky ones?

There's also a question about what happens when the semantic memory fills up. At 30 entries, the oldest lessons start dropping out. That's fine for recent knowledge, but what about deep lessons — things the agent learned in tick 10 that still apply in tick 200? The current design doesn't distinguish between "stale knowledge" and "foundational knowledge." At some point, that distinction will matter.

And compression every 10 ticks is a design choice, not a law. An agent in a rapidly changing environment might need faster compression. One in a stable environment might not need it at all. The fixed schedule is pragmatic, but it's a parameter worth watching.

## What's next

The memory system now exists. The deeper question is whether agents actually use it well — whether the `[KNOW]` section in the prompt changes how they reason, or whether it's just more text that the LLM attends to weakly. That's an empirical question, and the audit system exists now to start answering it. Running before/after comparisons with and without semantic memory enabled would tell you something real about whether the compression is earning its keep.
