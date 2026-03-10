---
title: "Day 28: A Stricter Conversation"
date: 2026-03-10
tags: [llm, infrastructure, phase-4]
pr: 28
---

I have spent a lot of time cleaning up after models that almost answered in JSON. Not wildly wrong, just wrong in all the tedious ways that make systems feel brittle: extra text, malformed objects, strange characters, little acts of sloppiness that force the rest of the codebase to become a janitor. I wanted the conversation between the simulation and the model to get stricter.

## What I built

This PR moved the project onto an OpenAI-compatible serving path and leaned into structured outputs instead of hoping for them. Agent decisions, oracle judgments, item effects, and memory compression all gained explicit schemas, so the model is now asked to speak inside a defined shape rather than being politely reminded to "please return valid JSON."

I still kept defensive cleanup around the edges, because production reality rarely stays pure. Responses are sanitized for control characters and trimmed down to the actual JSON object when extra text slips through. But the center of gravity changed. The parser is no longer trying to guess the model's intent after the fact. The contract is tighter from the start.

## Why it matters

As the simulation gets more social and more long-running, brittle model I/O becomes a structural problem, not a nuisance. A single malformed response can ripple into failed actions, broken memory updates, or inconsistent world judgments. Stronger structure reduces that fragility and makes the rest of the system less dependent on handwritten recovery tricks.

## Things to consider

There is always a tradeoff when the output shape gets stricter. Reliability goes up, but so does the amount of meaning I am defining ahead of time. A schema is not neutral. It says what kinds of answers the world is prepared to hear. That can protect the simulation from nonsense, but it can also narrow the weirdness that sometimes makes agent behavior feel alive.

Changing the serving backend also changes the personality of the system in ways that are easy to underestimate. Even if the prompts stayed the same, the rhythm of responses, the failure modes, and the incentives inside the generation process have all shifted. Some of that will show up as cleaner logs. Some of it may show up as different behavior that looks like emergence until I inspect it more carefully.

## What's next

I expect this to make longer runs and richer interactions much less fragile, which is reason enough to do it. But the more interesting next step is comparative: now that the contract is firmer, I can watch more closely for what actually changes in agent behavior when the language pipeline itself becomes more disciplined. That feels like infrastructure work with philosophical side effects.
