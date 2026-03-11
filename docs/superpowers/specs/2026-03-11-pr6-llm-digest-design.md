# PR6 — LLM Digest Builder

**Date:** 2026-03-11
**Status:** Approved

## Context

PRs 1–5 of the metrics roadmap are complete. Each simulation run now produces `events.jsonl` (authoritative), `meta.json`, `metrics/summary.json`, `metrics/ebs.json`, and `blobs/`. PR6 adds `llm_digest/` — a post-run analysis layer that reads `events.jsonl` deterministically and produces structured digests for human inspection, LLM context loading, and cross-run comparison. No LLM calls in PR6. The optional LLM narrative overlay is deferred to a future PR.

## Design

### Hybrid strategy

- **Authoritative digest**: deterministic, reproducible, diffable, testable
- **LLM narrative layer** (future PR): renderer-only, constrained to read deterministic outputs + evidence snippets, must cite event/tick IDs, produces `run_digest_llm.md`

### Architecture: Composable pipeline

```
simulation/
  digest/
    __init__.py
    behavior_segmenter.py    # BehaviorSegmenter
    anomaly_detector.py      # AnomalyDetector
    evidence_indexer.py      # EvidenceIndexer
    digest_builder.py        # DigestBuilder (orchestrator) + __main__ entry
    digest_renderer.py       # DigestRenderer (writes JSON + MD)
```

### Output layout

```
data/runs/<run_id>/
  llm_digest/
    run_digest.json           # authoritative run-level index
    run_digest.md             # deterministic render
    evidence_index.json       # claim_id → [event_ids]
    generation_manifest.json  # provenance
    agents/
      Ada.json                # derived per-agent projection
      Ada.md
      Bruno.json
      Bruno.md
```

---

## Component Specifications

### BehaviorSegmenter

Classifies each agent tick into one of four behavioral modes, smooths over a rolling window, and merges into labeled phase segments.

**Input:** agent-filtered event list
**Output:** `AgentSegmentation`

```python
@dataclass
class TickModeScore:
    tick: int
    scores: dict[str, float]    # exploration/exploitation/innovation/maintenance
    assigned_mode: str
    dominant_signals: list[str]

@dataclass
class PhaseSegment:
    agent_id: str
    phase_id: int
    mode: str
    tick_start: int
    tick_end: int
    confidence: float
    dominant_signals: list[str]
    supporting_event_ids: list[str]

@dataclass
class AgentSegmentation:
    agent_id: str
    tick_scores: list[TickModeScore]
    phases: list[PhaseSegment]
```

#### Mode taxonomy

- `exploration` — repositioning into unknown/less-visited space, scouting
- `exploitation` — consuming/harvesting known resources, moving toward visible food
- `innovation` — attempting new actions, collecting for innovation prerequisites, executing custom actions
- `maintenance` — rest/recovery driven by night penalties, low energy, acute survival

#### Scoring rules (v1 deterministic)

| Signal | Exploration | Exploitation | Innovation | Maintenance |
|--------|-------------|--------------|------------|-------------|
| action=eat | — | +5 | — | — |
| action=rest | — | — | — | +5 |
| action=innovate | — | — | +6 | — |
| action=pickup, item in pending innovation | — | +1 | +2 | — |
| reason text: "explore/scout/unknown" | +3 | — | — | — |
| reason text: "fruit/food/hunger" | — | +3 | — | — |
| reason text: "craft/tool/knife/stick" | — | — | +3 | — |
| reason text: "night/conserve/energy cost" | — | — | — | +3 |
| move toward visible food | — | +2 | — | — |
| move toward requires.tile | — | — | +3 | — |
| night penalty active | — | — | — | +2 |
| energy < 30% | — | — | — | +2 |

#### Smoothing & hysteresis

- 5-tick trailing window on raw scores before mode assignment
- Enter new mode only if lead ≥ 2.0 over current mode for ≥ 3 consecutive ticks
- **Innovation burst exception:** 1 tick is sufficient if `innovation_attempt` or `custom_action_executed` is present
- Adjacent same-mode spans merged; spans < 3 ticks absorbed into neighbors (except innovation bursts)

---

### AnomalyDetector

**Input:** all events for the run
**Output:** `list[Anomaly]`

```python
@dataclass
class Anomaly:
    anomaly_id: str
    type: str      # LLM_FALLBACK | CONTRADICTION | REPEATED_FAILURE | UNUSUAL_PRECEDENT | PARSE_FAIL_STREAK
    severity: str  # high | medium | low
    tick: int
    agent_id: str | None
    description: str
    supporting_event_ids: list[str]
```

Detection rules:

| Type | Trigger | Severity |
|------|---------|----------|
| `LLM_FALLBACK` | `agent_decision.parse_ok == false` (signals LLM unavailable / fallback used — not a JSON parse failure per se) | medium |
| `CONTRADICTION` | Computed inline: a learning in `memory_compression_result.payload.learnings` matches a negation pattern (e.g. "no {resource}", "{action} never works") while events confirm the resource was consumed or the action succeeded earlier in the run | high |
| `REPEATED_FAILURE` | Same action type fails ≥ 3 times in ≤ 10 ticks for same agent (`oracle_resolution.success == false`) | medium |
| `UNUSUAL_PRECEDENT` | `oracle_resolution.cache_hit == false` on an innovate-type action (new precedent created) | low |
| `PARSE_FAIL_STREAK` | ≥ 3 consecutive `parse_ok == false` events for same agent | high |

**Contradiction detection detail:** The `AnomalyDetector` builds its own ground-truth cache from events (same approach as `ebs_builder.py:_check_contradiction()`). It tracks `resource_confirmed` (resource types seen in `resource_consumed` events) and `action_succeeded` (action types with `oracle_resolution.success == true`). It then checks each learning string for negation patterns against the ground-truth cache. No changes required to `event_emitter.py` or `memory.py`.

**Evidence index key format for anomalies:** Agent-scoped anomalies use `<agent_id>_anomaly_<type>_<tick>` (e.g. `Ada_anomaly_REPEATED_FAILURE_27`). Run-scoped anomalies (no `agent_id`) use `run_anomaly_<type>_<tick>` (e.g. `run_anomaly_UNUSUAL_PRECEDENT_14`).

---

### EvidenceIndexer

**Input:** all events + `AgentSegmentation` list + `list[Anomaly]`
**Output:** `evidence_index.json`

Maps every claim in the digest to the event IDs that support it.

Key format:
- Agent phase: `<agent_id>_phase_<phase_id>` (e.g. `Ada_phase_3`)
- Agent contradiction: `<agent_id>_contradiction_tick_<tick>`
- Agent anomaly: `<agent_id>_anomaly_<type>_<tick>`
- Run anomaly (no agent): `run_anomaly_<type>_<tick>`
- Critical event: `<agent_id>_critical_tick_<tick>`

```json
{
  "Ada_phase_3": ["evt_074", "evt_078", "evt_081"],
  "Ada_contradiction_tick_42": ["evt_042_memory"],
  "Ada_anomaly_REPEATED_FAILURE_27": ["evt_011", "evt_019", "evt_027"],
  "run_anomaly_UNUSUAL_PRECEDENT_14": ["evt_014_oracle"]
}
```

---

### DigestBuilder (orchestrator)

```python
class DigestBuilder:
    def __init__(self, run_dir: Path): ...
    def build(self) -> RunDigest
```

Reads `events.jsonl` once, dispatches to components, assembles `RunDigest`, passes to `DigestRenderer`.

---

### DigestRenderer

Pure serialization + inline string template rendering. No analysis logic. Each markdown section maps 1:1 to a JSON field.

Must have its own unit test (see Testing section).

---

## JSON Schemas

### `run_digest.json`

```json
{
  "run_id": "f8dfc657-...",
  "generated_at": "2026-03-11T14:22:00Z",
  "meta": {
    "seed": 42,
    "ticks": 72,
    "agent_count": 2,
    "world_size": [10, 10],
    "model_id": "qwen2.5:3b",
    "git_commit": "a925467"
  },
  "outcomes": {
    "survivors": ["Ada", "Bruno"],
    "deaths": [],
    "total_innovations_approved": 1,
    "total_innovations_attempted": 3,
    "total_anomalies": 2,
    "anomaly_counts_by_type": { "LLM_FALLBACK": 1, "REPEATED_FAILURE": 1 }
  },
  "agents": [
    {
      "agent_id": "Ada",
      "status": "alive",
      "phase_count": 5,
      "dominant_mode": "exploitation",
      "innovation_count": 1,
      "anomaly_count": 1,
      "digest_path": "agents/Ada.json"
    }
  ],
  "anomalies": [
    {
      "anomaly_id": "run_anomaly_UNUSUAL_PRECEDENT_14",
      "type": "UNUSUAL_PRECEDENT",
      "severity": "low",
      "tick": 14,
      "agent_id": "Ada",
      "description": "New oracle precedent created for innovate action at tick 14",
      "supporting_event_ids": ["evt_014_oracle"]
    }
  ],
  "evidence_path": "evidence_index.json",
  "manifest_path": "generation_manifest.json"
}
```

### `agents/Ada.json`

```json
{
  "agent_id": "Ada",
  "run_id": "f8dfc657-...",
  "status": "alive",
  "final_state": { "life": 88, "hunger": 12, "energy": 71, "pos": [4, 6] },
  "state_extrema": {
    "min_life": { "value": 61, "tick": 34 },
    "max_hunger": { "value": 89, "tick": 33 }
  },
  "action_mix": { "move": 0.52, "eat": 0.21, "rest": 0.18, "innovate": 0.09 },
  "phases": [
    {
      "phase_id": 1,
      "mode": "exploration",
      "tick_start": 1,
      "tick_end": 8,
      "confidence": 0.74,
      "dominant_signals": ["move_unknown_tile", "reason_explore"],
      "supporting_event_ids": ["evt_001", "evt_004", "evt_007"]
    }
  ],
  "tick_scores": [
    {
      "tick": 1,
      "scores": { "exploration": 0.61, "exploitation": 0.12, "innovation": 0.08, "maintenance": 0.19 },
      "assigned_mode": "exploration",
      "dominant_signals": ["move_unknown_tile"]
    }
  ],
  "innovations": [
    {
      "name": "craft_stone_knife",
      "tick_attempted": 47,
      "tick_first_used": 52,
      "approved": true,
      "category": "recipe_action",
      "structural_novelty": "inventory_enabler",
      "state_delta": { "hunger": -5, "energy": 8 }
    }
  ],
  "contradictions": [
    {
      "tick": 63,
      "learning": "trees have no food",
      "contradicted_by": "resource_consumed fruit at tick 14",
      "supporting_event_ids": ["evt_063_memory", "evt_014_consume"]
    }
  ],
  "anomalies": [
    {
      "anomaly_id": "Ada_anomaly_REPEATED_FAILURE_27",
      "type": "REPEATED_FAILURE",
      "severity": "medium",
      "tick": 27,
      "agent_id": "Ada",
      "description": "move_north failed 3 times between ticks 18–27",
      "supporting_event_ids": ["evt_018_oracle", "evt_022_oracle", "evt_027_oracle"]
    }
  ],
  "critical_events": [
    {
      "tick": 33,
      "description": "Near-death: life dropped to 61, hunger peaked at 89",
      "supporting_event_ids": ["evt_033_state"]
    }
  ]
}
```

### `generation_manifest.json`

All `source_files` paths are relative to `run_dir` root.

```json
{
  "mode": "deterministic",
  "generated_at": "2026-03-11T14:22:00Z",
  "digest_builder_version": "1.0.0",
  "source_files": {
    "events_jsonl": "events.jsonl",
    "meta_json": "meta.json",
    "ebs_json": "metrics/ebs.json"
  },
  "llm_overlay": null
}
```

When LLM overlay added (future PR):
```json
"llm_overlay": {
  "model_id": "claude-sonnet-4-6",
  "prompt_hash": "sha256:...",
  "temperature": 0.2,
  "generated_at": "..."
}
```

---

## CLI & Integration

### Canonical CLI

The `__main__` entry point is `simulation/digest/digest_builder.py`:

```bash
python -m simulation.digest.digest_builder data/runs/<run_id>
python -m simulation.digest.digest_builder data/runs/<run_id> --no-render-md
python -m simulation.digest.digest_builder data/runs/<run_id> --agents Ada Bruno
python -m simulation.digest.digest_builder data/runs/<run_id> --verbose
```

### Engine integration

`SimulationEngine` does not hold an `args` object. The `--no-digest` flag lives in `main.py` and is passed as a constructor parameter:

```python
# main.py
engine = SimulationEngine(..., run_digest=not args.no_digest)

# engine.py SimulationEngine.__init__
self.run_digest = run_digest  # new kwarg, default True
```

The DigestBuilder call is added in **both** post-run locations in `engine.py` where `MetricsBuilder` and `EBSBuilder` are already called — `run()` and `run_with_callback()` — wrapped in the same `try/except` pattern:

```python
if self.run_digest:
    try:
        from simulation.digest.digest_builder import DigestBuilder
        DigestBuilder(self.event_emitter.run_dir).build()
    except Exception as e:
        logger.warning(f"DigestBuilder failed: {e}")
```

`--no-digest` flag added to `main.py` argparse. Default: digest runs automatically.

---

## Testing

### `tests/test_behavior_segmenter.py`
- Pure exploration ticks → all phases `exploration`
- 1-tick `innovation_attempt` event → innovation burst phase created despite < 3 ticks
- Night-active + rest action → `maintenance` mode
- Cycling behavior → correct phase boundaries with hysteresis (no flickering)

### `tests/test_anomaly_detector.py`
- 3 consecutive `parse_ok == false` → `PARSE_FAIL_STREAK` (severity high)
- Same action fails 3× in 10 ticks → `REPEATED_FAILURE` (severity medium)
- Learning "no fruit" + confirmed fruit consumption → `CONTRADICTION` (severity high)
- New oracle precedent on innovate action → `UNUSUAL_PRECEDENT` (severity low)

### `tests/test_digest_renderer.py`
- Given a minimal `RunDigest` object, `DigestRenderer` writes `run_digest.md` with expected section headers and field values
- Given an `AgentDigest`, renderer writes `agents/<id>.md` with phases section and innovation timeline section
- Markdown output contains no placeholder strings like `None` or empty brackets where populated data is expected

### `tests/test_digest_builder.py` (integration)
- Synthetic events → `run_digest.json` validates against expected schema (all required keys present)
- All `supporting_event_ids` values appearing in agent digests and anomalies are present as keys in `evidence_index.json`
- Manifest: `mode == "deterministic"`, `llm_overlay == null`, all `source_files` paths use consistent relative format
- CLI: `python -m simulation.digest.digest_builder <tmpdir>` exits 0 and produces expected files

---

## Files

| Action | Path |
|--------|------|
| Create | `simulation/digest/__init__.py` |
| Create | `simulation/digest/behavior_segmenter.py` |
| Create | `simulation/digest/anomaly_detector.py` |
| Create | `simulation/digest/evidence_indexer.py` |
| Create | `simulation/digest/digest_builder.py` |
| Create | `simulation/digest/digest_renderer.py` |
| Create | `tests/test_behavior_segmenter.py` |
| Create | `tests/test_anomaly_detector.py` |
| Create | `tests/test_digest_renderer.py` |
| Create | `tests/test_digest_builder.py` |
| Modify | `simulation/engine.py` — add `run_digest` kwarg; add `DigestBuilder` call in both `run()` and `run_with_callback()` |
| Modify | `main.py` — add `--no-digest` flag; pass `run_digest=not args.no_digest` to engine |

**Reuse:** event-parsing pattern from `simulation/ebs_builder.py` (including the contradiction ground-truth cache logic); builder/test fixture pattern from `simulation/metrics_builder.py`.

---

## Verification

```bash
pytest tests/test_behavior_segmenter.py tests/test_anomaly_detector.py tests/test_digest_renderer.py tests/test_digest_builder.py -v
uv run main.py --no-llm --ticks 20 --agents 2 --seed 42
ls data/runs/*/llm_digest/
python -m simulation.digest.digest_builder data/runs/<latest_run_id>
cat data/runs/<latest_run_id>/llm_digest/run_digest.json
cat data/runs/<latest_run_id>/llm_digest/agents/Ada.md
pytest -m "not slow"
```
