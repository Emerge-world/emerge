---
title: "Day 15: Carrying what matters"
date: 2026-03-05
tags: [inventory, agents, phase-2]
pr: 15
---

Agents lived tick by tick. A fruit appeared on a tree, they walked to it, they ate it, it was gone — from the world and from them. Nothing accumulated. Nothing was saved for later. The agent making a decision in tick 40 had no more resources than the agent in tick 1, because the world reset their hands with every action. I wanted to give them pockets.

## What I built

The core of this PR is an `Inventory` class — quantity-based, capped at ten total items across all types. An agent carrying three fruits and two stones is holding five of their ten slots. It's simple arithmetic, but the simplicity is intentional: the inventory needs to be legible to the LLM in a single line, and a per-type count with a total is exactly that. When an agent has items, their decision prompt shows the inventory. When they're empty-handed, the line disappears entirely. The prompt stays clean until it needs to say something.

To fill the inventory, there's a new base action: `pickup`. It collects one item from whatever resource exists on the agent's current tile, deposits it into the inventory, and removes it from the world. No energy cost — holding something shouldn't be exhausting. Every agent starts with this action by default, without needing to innovate it. The pickup is a primitive, not an achievement.

The more interesting addition is in the innovation system. Innovations can now declare prerequisites — not just action types, but specific items the agent must be carrying. If an agent wants to innovate an action that `requires: {items: {stone: 2, wood: 1}}`, the oracle checks the inventory before the LLM runs. No items, no attempt. This isn't crafting yet — items aren't consumed when the innovation fires — but it's the precondition for crafting. The gate exists; the cost mechanism comes next.

## Why it matters

The relationship between an agent and the world just became stateful in a new way. What they're carrying is part of who they are in this tick. An agent with stone in their inventory is a different kind of agent from one with empty hands — not because their stats are different, but because their options are. They can attempt innovations that others can't. They've deferred consumption for potential future use. That's a rudimentary form of planning.

It also closes a loop that the terrain PR opened. Now that forests spawn mushrooms and mountains produce stone, those resources can be collected and carried. The terrain creates supply; the inventory creates demand. The fact that different tiles produce different materials means that an agent's inventory reflects where they've been. Geography starts to matter not just as a hazard to navigate but as a place to go and gather from.

## Things to consider

`pickup` costs nothing. That feels right from a gameplay perspective — the action is already costly in opportunity cost, since it means not moving or eating — but it creates an asymmetry worth watching. Eating is immediate and consuming: the resource is gone, the hunger is addressed. Carrying is free and deferred: the resource is gone from the world, but the benefit is withheld until something uses it. Will agents figure out when deferring is worth it? Or will they hoard without purpose, filling their inventory with things they never use?

The bigger tension is in `requires.items`. Right now, the oracle validates that an agent has the items needed to unlock an innovation, but those items are never consumed. That gap is deliberate — crafting is a separate feature — but it means agents can repeatedly trigger item-gated innovations without ever paying the resource cost. When crafting arrives, closing that loop will be the first thing it needs to do. Until then, there's a slight unreality to prerequisites: they check but don't cost.

There's also the question of what inventory means to the agent's self-model. The prompt shows what they're carrying, but agents don't yet have a vocabulary for why they picked something up or what they intend to do with it. That could produce pickup behavior that's random rather than intentional — they collect because the action exists, not because they have a plan. Whether that resolves on its own through accumulated experience, or whether the prompts need to frame inventory in terms of purpose, is an open question.

## What's next

Crafting is the obvious next step — giving items a use beyond unlocking innovations. An agent carrying stone and wood should be able to produce something: a tool, a structure, an artifact with ongoing effects. The inventory is a staging area; crafting is what it's staging for. Once there's a crafting action, the whole chain from terrain to resource to inventory to tool to survival becomes testable as a complete loop. That's what Phase 2 has been building toward: agents who don't just react to the world but transform it, one small material at a time.
