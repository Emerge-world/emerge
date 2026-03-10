# PR2: meta.json + blob references

## Context

PR1 (EventEmitter, now merged on `feat/event-emitter`) established the canonical
`events.jsonl` + `meta.json` run artifact under `data/runs/<run_id>/`. PR2 enriches
that artifact with two things the metrics plan requires:

1. **Richer `meta.json`** — git commit hash, per-template prompt SHA-256 hashes, separate
   agent/oracle model IDs, and the precedents file path. Makes runs reproducible and
   comparable.
2. **Blob references in events** — rendered prompts and raw LLM responses stored as files
   under `blobs/`, referenced from `agent_decision` and `oracle_resolution` events.
   Keeps JSONL compact while preserving full LLM traces for debugging and LLM digests.

---

## Design decisions

| Decision | Choice |
|---|---|
| Blob scope | Both agent decisions AND oracle LLM calls |
| Blob naming | Sequential (`prompt_<tick>_<agent>.txt`) with SHA-256 dedup |
| Model fields | Separate `agent_model_id` and `oracle_model_id` |
| Oracle blob refs location | Into existing `oracle_resolution` events (+ new `cache_hit` bool) |
| Ownership | EventEmitter owns all blob I/O via private `_write_blob()` |

### Dedup rule
`_write_blob(subdir, name, content)`:
1. Compute `sha256` of content
2. If sha256 already in `self._blob_sha_map` → return existing path (no write)
3. Else write `blobs/{subdir}/{name}.txt`, add to map

Oracle context names sanitized: `re.sub(r'[^a-zA-Z0-9_]', '_', ctx)[:40]`

---

## Output layout

```
data/runs/<run_id>/
  meta.json
  events.jsonl
  blobs/
    prompts/
      prompt_<tick>_<agent>.txt        # system + "\n\n---\n\n" + user
      oracle_<tick>_<context>.txt
    llm_raw/
      resp_<tick>_<agent>.txt
      oracle_resp_<tick>_<context>.txt
```

---

## meta.json schema (final)

```json
{
  "run_id": "...",
  "seed": 42,
  "width": 15, "height": 15, "max_ticks": 100,
  "agent_count": 3, "agent_names": ["Ada", "Bruno", "Clara"],
  "agent_model_id": "qwen2.5:3b",
  "oracle_model_id": "qwen2.5:3b",
  "git_commit": "ae65458",
  "prompt_hashes": {
    "agent/system": "...", "agent/decision": "...",
    "oracle/physical_system": "...", "oracle/innovation_system": "...",
    "oracle/custom_action_system": "...", "oracle/item_eat_effect": "...",
    "oracle/fruit_effect": "..."
  },
  "precedents_file": "data/precedents_42.json",
  "created_at": "2026-03-10T..."
}
```

Note: `model_id` renamed to `agent_model_id`.

---

## Event payload changes

`agent_decision` payload (blob fields present when LLM called, absent under `--no-llm`):
```json
{
  "parsed_action": {...}, "parse_ok": true, "action_origin": "base",
  "prompt_ref": "blobs/prompts/prompt_1_Ada.txt",
  "prompt_sha256": "abc123...",
  "raw_response_ref": "blobs/llm_raw/resp_1_Ada.txt",
  "response_sha256": "def456..."
}
```

`oracle_resolution` payload (blob fields null on cache hits):
```json
{
  "success": true,
  "effects": {"hunger": -20, "energy": 0, "life": 0},
  "cache_hit": true,
  "prompt_ref": null, "prompt_sha256": null,
  "raw_response_ref": null, "response_sha256": null
}
```

---

## Critical files

| File | Change |
|---|---|
| `simulation/event_emitter.py` | Main changes: new `__init__` params, `_write_blob()`, updated emit methods |
| `simulation/oracle.py` | Add `last_llm_trace`, `last_llm_context`, `last_cache_hit` attributes |
| `simulation/engine.py` | Thread new params to EventEmitter init + emit calls |
| `tests/test_event_emitter.py` | Tests for blob writing, dedup, new meta fields |

---

## Implementation steps

### Step 1 — `EventEmitter.__init__` signature + meta.json

**File:** `simulation/event_emitter.py`

Add parameters:
- `oracle_model_id: str`
- `precedents_file: Optional[str]`

Remove `model_id`, replace with `agent_model_id` in both signature and meta dict.

At init:
1. Compute `git_commit`:
   ```python
   import subprocess
   try:
       git_commit = subprocess.check_output(
           ["git", "rev-parse", "--short", "HEAD"],
           stderr=subprocess.DEVNULL
       ).decode().strip()
   except Exception:
       git_commit = "unknown"
   ```

2. Compute `prompt_hashes` from `prompts/` directory:
   ```python
   import hashlib
   from pathlib import Path
   prompts_dir = Path("prompts")
   prompt_hashes = {}
   for f in sorted(prompts_dir.rglob("*.txt")):
       key = str(f.relative_to(prompts_dir).with_suffix(""))
       content = f.read_text(encoding="utf-8")
       prompt_hashes[key] = hashlib.sha256(content.encode()).hexdigest()
   ```
   Skip `old_system` if present (it's deprecated).

3. Create blob subdirs:
   ```python
   (run_dir / "blobs" / "prompts").mkdir(parents=True, exist_ok=True)
   (run_dir / "blobs" / "llm_raw").mkdir(parents=True, exist_ok=True)
   ```

4. Init dedup map: `self._blob_sha_map: dict[str, str] = {}`  (sha256 → rel path str)

5. Write enriched meta.json.

---

### Step 2 — `_write_blob()` helper

**File:** `simulation/event_emitter.py`

```python
def _write_blob(self, subdir: str, name: str, content: str) -> tuple[str, str]:
    """Write content to blobs/{subdir}/{name}.txt with SHA-256 dedup.

    Returns (relative_path, sha256). If an identical blob already exists,
    returns the existing path without writing.
    """
    import hashlib
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if sha in self._blob_sha_map:
        return self._blob_sha_map[sha], sha
    rel = f"blobs/{subdir}/{name}.txt"
    path = Path("data") / "runs" / self.run_id / rel
    path.write_text(content, encoding="utf-8")
    self._blob_sha_map[sha] = rel
    return rel, sha
```

---

### Step 3 — Update `emit_agent_decision`

**File:** `simulation/event_emitter.py`

Add `llm_trace: Optional[dict] = None` parameter.

```python
payload: dict = {
    "parsed_action": action,
    "parse_ok": parse_ok,
    "action_origin": self._action_origin(action_name),
}
if llm_trace:
    combined_prompt = llm_trace["system_prompt"] + "\n\n---\n\n" + llm_trace["user_prompt"]
    p_ref, p_sha = self._write_blob("prompts", f"prompt_{tick}_{agent_name}", combined_prompt)
    r_ref, r_sha = self._write_blob("llm_raw", f"resp_{tick}_{agent_name}", llm_trace["raw_response"])
    payload["prompt_ref"] = p_ref
    payload["prompt_sha256"] = p_sha
    payload["raw_response_ref"] = r_ref
    payload["response_sha256"] = r_sha
```

---

### Step 4 — Update `emit_oracle_resolution`

**File:** `simulation/event_emitter.py`

Add `llm_trace: Optional[dict] = None`, `oracle_context: Optional[str] = None`,
`cache_hit: bool = True` parameters.

```python
import re
payload: dict = {
    "success": result["success"],
    "effects": {...},
    "cache_hit": cache_hit,
    "prompt_ref": None,
    "prompt_sha256": None,
    "raw_response_ref": None,
    "response_sha256": None,
}
if llm_trace and oracle_context:
    safe_ctx = re.sub(r'[^a-zA-Z0-9_]', '_', oracle_context)[:40]
    combined_prompt = llm_trace["system_prompt"] + "\n\n---\n\n" + llm_trace["user_prompt"]
    p_ref, p_sha = self._write_blob("prompts", f"oracle_{tick}_{safe_ctx}", combined_prompt)
    r_ref, r_sha = self._write_blob("llm_raw", f"oracle_resp_{tick}_{safe_ctx}", llm_trace["raw_response"])
    payload["prompt_ref"] = p_ref
    payload["prompt_sha256"] = p_sha
    payload["raw_response_ref"] = r_ref
    payload["response_sha256"] = r_sha
```

---

### Step 5 — Oracle instrumentation

**File:** `simulation/oracle.py`

At the top of `resolve_action()`, reset:
```python
self.last_llm_trace: Optional[dict] = None
self.last_llm_context: Optional[str] = None
self.last_cache_hit: bool = True
```

After each LLM call in the 5 oracle paths, set context strings:
- `_oracle_reflect_physical()` → `"physical_reflect"`
- `_resolve_innovate()` (validation) → `f"validate_innovation_{action_name}"`
- `_resolve_custom_action()` → `f"custom_action_{action_name}"`
- `_get_item_eat_effect()` → `f"item_eat_{item_type}"`
- fruit effect path → `"fruit_effect"`

And set:
```python
self.last_llm_trace = self.llm.last_call.copy()
self.last_llm_context = "<context string>"
self.last_cache_hit = False
```

---

### Step 6 — Engine wiring

**File:** `simulation/engine.py`

**Init:** update `EventEmitter(...)` call with new params:
- rename `model_id=` → `agent_model_id=`
- add `oracle_model_id=oracle.model_id` (or however oracle exposes its model)
- add `precedents_file=oracle.precedents_path` (or the path string)

**Agent decision** (around line 213): `_llm_trace` already extracted — pass it:
```python
event_emitter.emit_agent_decision(tick, agent.name, action, parse_ok, llm_trace=llm_trace)
```

**Oracle resolution**: read oracle attributes after `resolve_action()`:
```python
event_emitter.emit_oracle_resolution(
    tick, agent.name, result,
    llm_trace=oracle.last_llm_trace,
    oracle_context=oracle.last_llm_context,
    cache_hit=oracle.last_cache_hit,
)
```

---

### Step 7 — Tests

**File:** `tests/test_event_emitter.py`

Add tests for:
1. `meta.json` has `agent_model_id`, `oracle_model_id`, `git_commit`, `prompt_hashes`, `precedents_file`
2. `_write_blob()` writes file on first call, returns same path on second call with identical content (dedup)
3. `emit_agent_decision` with `llm_trace` → blob files exist, event payload has refs
4. `emit_agent_decision` without `llm_trace` → no blob fields in payload
5. `emit_oracle_resolution` with `cache_hit=True` → null blob refs, `cache_hit: true`
6. `emit_oracle_resolution` with `llm_trace` → blob files exist, `cache_hit: false`

---

## Verification

```bash
# Smoke test — blobs directory should appear, meta.json should have new fields
uv run main.py --no-llm --ticks 5 --agents 1
cat data/runs/$(ls -t data/runs | head -1)/meta.json

# Full run — agent and oracle blobs should be written
uv run main.py --agents 2 --ticks 10 --seed 42
ls data/runs/$(ls -t data/runs | head -1)/blobs/prompts/
ls data/runs/$(ls -t data/runs | head -1)/blobs/llm_raw/
cat data/runs/$(ls -t data/runs | head -1)/events.jsonl | python3 -c "import sys,json; [print(e['event_type'], e.get('payload',{}).get('prompt_ref','—')) for e in map(json.loads, sys.stdin)]"

# Tests
uv run pytest tests/test_event_emitter.py -v
uv run pytest -m "not slow"
```

---

## Cornerstone updates

After PR merges, update:
- `project-cornerstone/00-master-plan/DECISION_LOG.md` — add DEC-031 for blob references design
- `project-cornerstone/01-architecture/architecture_context.md` — note `blobs/` in run layout