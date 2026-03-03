---
title: "Day 11: When invention means something"
date: 2026-03-03
tags: [innovation, oracle, emergence, phase-1]
pr: 11
---

Innovation was already in the code. It had been there since the beginning — agents could ask the oracle to approve a new action, and if it passed, it got added to their repertoire. But it felt hollow. An agent could invent anything, for free, with no constraints, and the oracle would dutifully stamp it and move on. Nothing was at stake. No friction, no structure. And without friction, there's no meaning.

## What I built

Four changes, shipped together, because they only make sense as a set.

First: prerequisites. Agents can now declare what they need before trying to invent something. An agent who wants to learn to fish should be standing near water. One who wants to build a shelter should have enough energy to try. These checks happen before the oracle even consults its LLM — fast, cheap, and honest. If the conditions aren't right, the agent gets feedback and can try later.

Second: effect bounds. Before this, when the oracle approved an innovation and estimated its effects, it could return anything. Hunger drop of a thousand. Energy gain of fifty. The numbers were unconstrained, which made them meaningless. Now there's a sensible ceiling and floor on every stat delta — not generous enough to be exploitable, not stingy enough to make innovation pointless.

Third: categories. The oracle now classifies every approved innovation: SURVIVAL, CRAFTING, EXPLORATION, or SOCIAL. Just a label — but it starts to give shape to the action space. You can see, in the logs, what kind of world the agents are building in their heads.

Fourth: redundancy prevention. The existing action list is passed to the oracle's validation prompt. An agent who already knows how to "gather_berries" can't invent "pick_berries" and get away with it. The oracle knows the difference between a genuinely new capability and a rename.

And one small but important number: the energy cost for innovation went from zero to ten.

## Why it matters

Emergence — the whole point of this project — only happens when actions have consequences. Before this PR, innovation was essentially free speculation. An agent could shotgun a dozen invented actions per session with no downside. That's not creativity, it's spam.

The constraints don't limit what agents can invent. They shape the conditions under which invention is meaningful. An agent who has saved up enough energy, found the right tile, and hasn't already invented something equivalent — that agent's innovation tells you something real about how they're reading the world. The oracle's judgment matters more when there's something to judge.

## Things to consider

Categories are interesting and slightly dangerous. CRAFTING implies tools. EXPLORATION implies maps. SOCIAL implies other agents to signal to. These categories are labeling a future that doesn't exist yet in the simulation. An agent could invent "make_spear" and get a CRAFTING tag — but there's no inventory, no materials, no way to actually use a spear. The category is a promise the world hasn't kept yet.

Does that matter? Maybe not yet. But as the action space fills up with CRAFTING innovations that have no real substrate, there's a risk that agents develop a kind of false confidence — a rich vocabulary of actions that are, underneath, just slightly different variations on "do something on this tile." The prerequisites help, but only for physical context, not for material state.

There's also a subtler question about the oracle as gatekeeper. Now that it validates semantic novelty — checking whether a new action is genuinely different from what already exists — it's making aesthetic judgments, not just physical ones. The oracle's idea of "meaningfully different" is the model's idea. If qwen3.5:4b has a particular clustering of conceptual similarity, the innovation space will have that shape too, invisibly.

## What's next

The action space is starting to grow. A few sessions from now, an agent might have five, eight, ten innovated actions alongside the four base ones. The memory system — episodic and semantic — was built partly to handle this: agents should be able to remember not just *what* they've invented, but *when it's useful*.

That's the next layer. Not more structure around innovation, but better integration between the things agents know and the situations they're in. The categories give us a way to think about this — an agent in a SURVIVAL crisis probably shouldn't be spending energy on EXPLORATION innovations. Whether they actually reason that way depends on what the memory compression produces and what the LLM does with it.

What's become visible now is that the innovation system and the memory system are deeply entangled. They're two halves of the same problem: how does an agent build a cumulative model of the world from experience? Innovation is how the model expands. Memory is how it persists. We've improved both in Phase 1. What we haven't done yet is made them talk to each other well.
