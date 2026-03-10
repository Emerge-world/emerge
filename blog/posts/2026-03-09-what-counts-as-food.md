---
title: "Day 24: What Counts as Food"
date: 2026-03-09
tags: [oracle, survival, phase-4]
pr: 24
---

The more items and terrain types I added, the more embarrassing the old eating logic started to feel. The world was getting richer, but hunger still lived inside a tiny box. Fruit was food, everything else was effectively a wall, and that stopped making sense the moment mushrooms, water, and other materials entered the simulation. I wanted the question of edibility to belong to the world, not to a hardcoded special case.

## What I built

This PR generalized eating so the oracle can judge any nearby item type instead of only fruit. Each resource now gets its own precedent about whether it is edible, how much hunger it relieves, and whether it helps or harms life. Once the world has made that judgment, it remembers it and applies it consistently from then on.

That sounds small, but it changes the feel of the system. Agents can fail differently now. They are no longer told merely that fruit is absent. They are told, in effect, that the nearby world contains things which may or may not belong inside a body. That pushes survival a little closer to interpretation and away from a static lookup table.

## Why it matters

Emergence depends on categories becoming discoverable through interaction. If the world contains many materials but only one official food, then those materials are mostly decorative. By generalizing eating, I made the simulation more honest about the fact that a resource ecology should include uncertainty, risk, and precedent, not just abundance counts.

## Things to consider

There is a conceptual mismatch hiding here that I can already feel. Water can now reduce hunger because hunger is the only appetite-like meter the simulation has. That is useful in the short term, but it also exposes the absence of thirst as a distinct need. Generalizing one action can make missing systems more visible rather than less.

There is also a precedent problem. Once the oracle decides what eating a given item means, that ruling becomes stable, but perhaps too stable. Context does not matter yet. A mushroom is a mushroom whether the agent is starving, whether it was prepared, or whether the world should have room for rare exceptions. The gain is consistency. The cost is a world that may learn its categories too quickly and too absolutely.

## What's next

This opens the door to a more believable material world. If items can differ in nutrition, danger, and usefulness, then hunger can start to push agents toward experimentation instead of toward the same safe loop every time. It also sharpens the case for new needs and new risks. The question is no longer just what agents can eat, but how fine-grained I want the world to become once that question matters.
