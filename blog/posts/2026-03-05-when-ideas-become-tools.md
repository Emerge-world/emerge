---
title: "Day 17: When ideas become tools"
date: 2026-03-05
tags: [crafting, innovation, phase-2]
pr: 17
---

I could feel the gap after inventory landed. Agents could carry stone, wood, fruit, but carrying is not the same as doing. Their pockets were full of possibility, and the simulation still had no honest way to turn that possibility into something new. I wanted materials to matter, not just as prerequisites in a prompt, but as things that could be spent and transformed.

## What I built

This PR closes the loop that inventory opened. Agents can now propose crafting as part of innovation itself, by describing not only what an action requires but what it produces. If an agent invents a way to shape stone into a knife, the world remembers that recipe as part of the action, not as a hardcoded exception. I did not add a universal craft button. I let crafting emerge through the same channel as every other new behavior.

The important shift is where responsibility lives. The oracle still decides whether a new idea makes sense in a primitive world, but once the idea is approved, the recipe stops being fuzzy. Required materials are checked deterministically before the action runs. If the agent has what it needs, those items are consumed, the labor cost is applied, and the produced item is added to inventory. If the agent does not have the materials, the action fails early without another model call.

I also tightened the boundary around what the model is allowed to decide. For crafting actions, it only judges the cost and outcome of the physical labor. It does not get to invent extra item changes on the fly. That part is handled by code, every time, the same way. Later fixes in the branch made that boundary stricter: materials are only spent when the action actually succeeds, cached precedents still respect consumption and production, and full inventories can cause crafted items to be lost instead of silently appearing from nowhere.

There is a small design choice in here that I like more the longer I look at it: failure messages stay generic when materials are missing. The world says you lacked what was needed, but it does not enumerate the exact missing ingredient for you. That keeps the simulation from turning into a tooltip system. The agent has to live inside the world, not above it.

## Why it matters

This is the first time Emerge lets agents convert gathered resources into durable new capability without me prescribing recipes ahead of time. That matters because it keeps the center of gravity where I want it: emergence over prescription. I am not teaching the simulation that stone plus wood equals spear. I am giving agents a way to propose that relationship, and giving the world a way to accept or reject it consistently.

It also makes Phase 2 feel real. Terrain creates resources, inventory lets agents carry them, and now crafting lets those resources become tools. That is a much richer survival loop than eat or rest. Once an agent can turn what it found yesterday into an advantage tomorrow, time starts to matter in a different way. Planning becomes thinkable.

## Things to consider

The more I lean on precedents, the more I have to ask what a precedent is allowed to ignore. Right now a custom crafting action is still remembered in a fairly coarse way. That is enough for basic recipes, but what happens when the quality of the materials matters, or when the same action should behave differently depending on what tool the agent already has? A stable world needs consistency, but too much flattening can make the world feel less real.

There is also a tension in the decision to keep missing-material feedback vague. I like that it preserves mystery and avoids leaking hidden rule details. But if agents repeatedly fail without understanding why, does that create productive experimentation or just noise? Human players would call that opacity. For artificial agents, it might be exactly the kind of friction that produces more interesting behavior. I do not know yet.

And then there is the inventory itself. If a crafted item is lost because the inventory is full, that is honest in a systems sense, but it hints at a bigger question: when does the simulation need a notion of dropping, placing, or reserving space? Once agents can make tools, losing them to capacity limits stops feeling like a minor inconvenience and starts feeling like a behavioral pressure.

## What's next

Now that materials can become tools, I can start caring about what tools actually unlock. A knife that exists only as an inventory count is a proof of concept. A knife that changes what actions are possible, how effective they are, or what kinds of resources an agent can access starts to pull the simulation toward culture and technology. The interesting part is not the first crafted object. It is the chain of consequences that follows once crafted objects matter.

I also think this changes how I look at innovation itself. Up to now, innovation has mostly been about naming new behaviors and giving them bounded effects. With crafting in place, an innovation can leave something behind. It can create a persistent artifact. That feels like the start of a different kind of memory in the world, where ideas do not just change stats for a tick, but accumulate into a material history.
