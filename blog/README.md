# Emerge Devlog

A developer diary tracking the evolution of the Emerge simulation project — a world where LLM-controlled agents try to survive, innovate, and eventually develop culture without hardcoded rules.

Posts are written in Obsidian-compatible Markdown and live in `posts/`. Each post covers one merged PR.

## Reading the blog

Open the `posts/` folder in Obsidian, or serve locally with [Quartz](https://quartz.jzhao.xyz/):

```bash
# From this directory (emerge/blog/)
npx quartz create      # one-time setup: bootstrap Quartz
npx quartz build --serve   # serves at http://localhost:8080
```

## Post format

Each post follows this structure:

```
---
title: "Day N: <human title>"
date: YYYY-MM-DD
tags: [feature, module, phase-N]
pr: N
---

Opening paragraph — the human moment.

## What I built
## Why it matters
## Things to consider
## What's next
```

**Tone:** First person, diary-style. Written as if explaining to a curious friend who knows the project. No raw class names or function signatures unless they're the point.

## Generating a post

From the `emerge/` directory, invoke the Claude Code skill:

```
/blog          # generates post for the most recent merged PR
/blog 11       # generates post for PR #11
```

The skill reads the git diff, commit history, and relevant `project-cornerstone/` context files to write the narrative.

## Contributing posts

After every PR is merged, run `/blog` before starting the next feature. Commit the post with:

```
git add blog/posts/<filename>.md
git commit -m "docs(blog): add devlog post for PR #N"
```
