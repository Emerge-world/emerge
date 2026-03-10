---
title: "Day 27: Runs That Belong Together"
date: 2026-03-10
tags: [experiments, tooling, phase-4]
pr: 27
---

As soon as experiment tracking existed, the next weakness became obvious. I could observe runs much better than before, but I was still launching them like one-off errands. Change a seed, rerun. Change the number of agents, rerun. Change the model, rerun. It was too easy for "comparison" to mean a pile of manually typed commands and half-remembered intent.

## What I built

This PR added a small batch runner driven by a YAML file. Instead of retyping the whole command line for every variation, I can describe a set of experiments declaratively, expand repeated runs automatically, and execute each one in its own isolated subprocess. Each run gets a stable name, and that name is passed through to experiment tracking so the batch shows up as a coherent set instead of a blur.

I chose sequential subprocesses on purpose. It is slower than a more aggressive design, but it keeps each run isolated from the others and avoids turning debugging into a concurrency problem. If one experiment fails, the rest continue, and the summary at the end makes the shape of the batch visible.

## Why it matters

This is less glamorous than a new mechanic, but it changes how the project can be used. Emerge is starting to behave like a research instrument as much as a simulation toy. That means repeatability matters. A batch runner turns vague curiosity into named, rerunnable experiments and makes comparison part of the workflow instead of an afterthought.

## Things to consider

There is a maintenance cost baked into this kind of convenience. The list of allowed configuration keys has to stay aligned with the real command-line interface, or the tool becomes a quiet source of drift. That sounds minor until the day a new flag exists in one place but not the other and a whole batch is operating on stale assumptions.

I also chose resilience over strictness by letting failed runs be recorded and skipped rather than aborting the whole batch. I still think that is the right call, but it creates a subtle risk: failure can become background noise. A batch that "mostly ran" is not the same as an experiment that supports a clean conclusion.

## What's next

With named batches and tracked runs, I can finally start asking broader questions without building a custom ritual around every comparison. That probably means more parameter sweeps, more repeated seeds, and eventually a clearer line between exploratory play and actual evidence. The machinery for that distinction is starting to exist now.
