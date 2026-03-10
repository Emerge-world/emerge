# Missing PR Devlogs Design

## Goal

Create missing developer diary posts for merged PRs `#19`, `#20`, `#21`, `#22`, `#24`, `#26`, `#27`, and `#28` in the Emerge project.

## Scope

- Work in an isolated git worktree under `.worktrees/`.
- Add one new post per missing merged PR.
- Keep each post compact, roughly `300-500` words.
- Preserve the existing devlog template and metadata fields.
- Give `Things to consider` more weight than the other body sections.

## Approach

For each PR, use the merge commit as the source of truth. Inspect the parent SHAs, diff stat, commit list, key diffs, and only the cornerstone documents that match the changed areas. Use that material to write a first-person diary entry that stays reflective rather than technical.

The posts should read as a chronological continuation of the existing blog. To keep the series coherent, research and draft the entries from oldest missing PR to newest.

## Constraints

- This is a docs-only pass. No product code changes are in scope.
- The worktree baseline is not fully green: `uv run pytest` currently fails in `tests/test_llm_client.py::TestGenerateStructured::test_guided_json_schema_passed_to_api`.
- Existing uncommitted changes in the main workspace must remain untouched.

## Output

- `blog/posts/YYYY-MM-DD-<slug>.md` files for each missing PR
- No commit unless explicitly requested later
