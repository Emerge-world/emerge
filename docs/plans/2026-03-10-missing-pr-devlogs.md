# Missing PR Devlogs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add compact devlog posts for every merged PR that does not yet have a blog entry.

**Architecture:** Use merge commits as the canonical record for each PR, derive filenames from merge dates, and write posts in chronological order so the blog reads like a continuous diary. Keep all entries brief while making `Things to consider` the reflective center of gravity.

**Tech Stack:** git, markdown, existing Emerge blog format

---

### Task 1: Capture source material for missing PRs

**Files:**
- Modify: `blog/posts/`
- Reference: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Reference: `project-cornerstone/01-architecture/architecture_context.md`
- Reference: `project-cornerstone/03-agents/agents_context.md`
- Reference: `project-cornerstone/04-oracle/oracle_context.md`
- Reference: `project-cornerstone/05-llm-integration/llm-integration_context.md`
- Reference: `project-cornerstone/06-innovation-system/innovation-system_context.md`

**Step 1: List uncovered merged PRs**

Run: `git log --merges --oneline --grep='Merge pull request #'`
Expected: merged PR list including `#19`, `#20`, `#21`, `#22`, `#24`, `#26`, `#27`, `#28`

**Step 2: For each PR, gather merge metadata**

Run: `git log --pretty=format:"%P" -n 1 <merge-sha>` and `git log -1 --format="%as" <merge-sha>`
Expected: base SHA, feature SHA, and merge date for each target PR

**Step 3: Inspect the changes**

Run: `git diff <base-sha>...<feature-sha> --stat`, `git log <base-sha>...<feature-sha> --oneline`, and `git diff <base-sha>...<feature-sha> -- simulation/ prompts/ server/ main.py`
Expected: enough context to identify the human story and the main tension for each PR

### Task 2: Draft the missing posts

**Files:**
- Create: `blog/posts/YYYY-MM-DD-<slug>.md`

**Step 1: Write compact entries from oldest PR to newest**

Write posts for `#19`, `#20`, `#21`, `#22`, `#24`, `#26`, `#27`, `#28`.

Expected: one post per PR, full template preserved, body kept compact

**Step 2: Weight the reflection correctly**

Make `Things to consider` the most substantial section after the opening.

Expected: posts feel like diary entries with clear open questions, not changelogs

### Task 3: Verify coverage and output

**Files:**
- Verify: `blog/posts/*.md`

**Step 1: Confirm every target PR now has exactly one post**

Run: `rg '^pr:' blog/posts -n`
Expected: entries for all existing PR-backed posts plus `19,20,21,22,24,26,27,28`

**Step 2: Review git status**

Run: `git status --short`
Expected: only the new plan/design docs and new blog posts are added in the worktree
