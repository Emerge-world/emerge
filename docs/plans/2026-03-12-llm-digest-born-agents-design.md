# LLM Digest Born Agents Design

**Date:** 2026-03-12

## Problem

`llm_digest` currently discovers agents by returning the initial `run_start.payload.config.agent_names` list as soon as it sees the `run_start` event. That excludes agents born later in the same run, so they do not appear in:

- `llm_digest/run_digest.json`
- `llm_digest/run_digest.md`
- `llm_digest/agents/<id>.json`
- `llm_digest/agents/<id>.md`

The digest also lacks lineage metadata for born agents, because `events.jsonl` does not currently emit a birth event with `generation`, `born_tick`, and `parent_ids`.

## Goals

- Include born agents in run-level and per-agent digests.
- Add lineage metadata for both initial settlers and born agents.
- Keep the digest deterministic and self-contained within the run directory.
- Preserve compatibility with older runs that do not have explicit birth events.

## Non-Goals

- No LLM overlay changes.
- No dependence on `data/lineage_<seed>.json` or other files outside the run directory.
- No broad event schema rewrite.

## Options Considered

### 1. Emit a dedicated `agent_birth` event and build lineage from `events.jsonl`

This adds a small canonical event with:

- `child_name`
- `generation`
- `born_tick`
- `parent_ids`
- `pos`

Pros:

- Exact lineage from the authoritative run event stream
- No dependency on external mutable files
- Minimal event-size impact

Cons:

- Requires a small event schema addition

### 2. Add lineage fields to every `agent_state` event

Pros:

- Digest extraction is simple

Cons:

- Repeats static metadata every tick
- Bloats `events.jsonl`

### 3. Read `data/lineage_<seed>.json` from the digest builder

Pros:

- Smallest builder patch in isolation

Cons:

- Breaks the digest contract by depending on data outside `run_dir`
- Makes digest reproducibility weaker for copied or archived run directories

## Decision

Use option 1.

Add a canonical `agent_birth` event and make `DigestBuilder` discover agents from the full event stream instead of the initial roster only.

## Design

### Canonical event changes

Add `EventEmitter.emit_agent_birth()` and call it in `SimulationEngine` immediately after `_spawn_child()` succeeds.

The event payload will include:

```json
{
  "child_name": "Kira",
  "generation": 1,
  "born_tick": 120,
  "parent_ids": ["Ada", "Bruno"],
  "pos": [4, 5]
}
```

Use `agent_id=child_name` so born agents become naturally visible in generic agent-scoped event scans.

### Digest agent discovery

Replace the current early-return logic with a full union of:

- initial agents from `run_start`
- born agents from `agent_birth`
- any non-null `agent_id` seen anywhere else in the run

Return a stable order:

1. initial settlers in `run_start` order
2. born agents in first-seen order
3. any remaining discovered IDs in sorted order

### Lineage extraction

Build a lineage index directly from events:

- Initial agents get:
  - `generation=0`
  - `born_tick=0`
  - `parent_ids=[]`
  - `is_born_agent=false`
- `agent_birth` provides exact lineage for born agents
- Older runs without `agent_birth` still include born agents if they appear in events, but lineage falls back to:
  - `generation=null`
  - `born_tick=null`
  - `parent_ids=[]`
  - `is_born_agent=false`

Malformed or partial birth payloads must not raise; they fall back to the same safe defaults.

### Digest output changes

Add lineage metadata to `run_digest.json` agent summaries:

- `generation`
- `born_tick`
- `parent_ids`

Add a top-level `lineage` object to each per-agent digest:

- `generation`
- `born_tick`
- `parent_ids`
- `is_born_agent`

### Markdown rendering

Update `run_digest.md` to show generation and born tick in the agents table.

Update per-agent markdown with a `## Lineage` section near the top:

- generation
- born tick
- parents, or `original settler` for generation 0

Avoid rendering `None` in markdown for older runs. Use `unknown` instead.

## Testing

Add integration coverage for a run where:

- `run_start` contains only `Ada`
- an `agent_birth` event later introduces `Kira`
- later events for `Kira` exist

Assert:

- `Kira` appears in `run_digest.json`
- `llm_digest/agents/Kira.json` exists
- `Kira` has the expected lineage metadata in JSON
- markdown renders generation/birth information

Also preserve compatibility by keeping current digest tests green.

## Risks

- Existing consumers might assume a fixed run-agent table shape. Adding keys is backward-compatible for JSON readers but markdown snapshots may need updates.
- Event ordering must remain deterministic. The birth event should be emitted immediately after child creation to avoid ambiguity.

## Success Criteria

- Born agents appear in run and per-agent digests.
- Their lineage metadata is present in both JSON and markdown.
- Older runs without `agent_birth` still digest successfully.
- Digest-focused tests and `pytest -m "not slow"` pass.
