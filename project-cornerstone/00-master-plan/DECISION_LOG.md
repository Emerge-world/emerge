# Decision Log

> Log of important technical decisions. Each entry is immutable once written.

## Format

```
### DEC-XXX: Title
- **Date**: YYYY-MM-DD
- **Context**: Why the decision arose
- **Decision**: What we decided
- **Rejected alternatives**: What else we considered
- **Consequences**: What this decision implies
```

---

### DEC-001: Initial LLM model
- **Date**: 2026-02-27
- **Context**: We need a model that runs locally, fast, and handles JSON.
- **Decision**: Qwen 2.5-3B via Ollama.
- **Rejected alternatives**: Llama 3 8B (too slow for 5 agents), Phi-3 (worse at JSON), GPT-4 API (cost).
- **Consequences**: Prompts must be concise. Responses in English. JSON parsing must be robust with fallbacks.

### DEC-002: Centralized oracle architecture
- **Date**: 2026-02-27
- **Context**: We need a consistent arbiter for actions.
- **Decision**: A central oracle with its own LLM + precedent system (dict in-memory).
- **Rejected alternatives**: Hardcoded rules (limits innovation), consensus between agents (too complex).
- **Consequences**: The oracle is a single point of failure. If its LLM fails, the entire simulation fails. Add deterministic fallbacks.

### DEC-003: Memory as list of strings
- **Date**: 2026-02-27
- **Context**: Agents need to remember what they've done.
- **Decision**: Simple list of strings with cap of 50 entries, FIFO.
- **Rejected alternatives**: Database per agent (overengineering), embeddings + RAG (Phase 1+).
- **Consequences**: Memory is volatile (lost between executions). In Phase 1 it must be persisted. The cap of 50 may be insufficient — monitor.

### DEC-004: Oracle physical reflection replaces hardcoded base-action rules
- **Date**: 2026-02-27
- **Context**: Agents were inventing actions (like diagonal movement) that the Oracle rejected programmatically without ever consulting its own LLM reasoning. The Oracle should embody world physics, not hardcode them.
- **Decision**: Remove hardcoded programmatic rules from base actions (move, eat, rest). All actions route through `_oracle_reflect_physical()`: the Oracle's LLM reasons about physical plausibility once per novel situation, then caches the result as a precedent. Move now supports all 8 compass directions (N/NE/E/SE/S/SW/W/NW).
- **Rejected alternatives**: Keep hardcoded rules but add diagonal support (doesn't fix the architectural inconsistency; Oracle bypasses its own reasoning).
- **Consequences**: ~4-6 new LLM calls on first run (one per tile type / action context). After warm-up, all base-action resolution is precedent-driven (no additional LLM calls). Fallback defaults apply when LLM is unavailable.

### DEC-005: Template-based prompt system
- **Date**: 2026-02-28
- **Context**: Prompt text was embedded directly in Python source, making iteration and experimentation slow.
- **Decision**: Prompts stored as `prompts/<module>/<name>.txt` with `$variable` substitution via `string.Template`. Loaded and cached by `simulation/prompt_loader.py`.
- **Rejected alternatives**: Jinja2 templates (unnecessary dependency for simple substitution), f-strings in code (hard to edit without touching logic).
- **Consequences**: All prompt changes require updating template files, not source files. `prompt_loader.py` caches templates on first load to avoid repeated disk reads.

### DEC-006: Markdown-based simulation logging (sim_logger.py)
- **Date**: 2026-02-28
- **Context**: structlog JSON lines were planned, but during early development a human-readable format was more valuable for manual inspection.
- **Decision**: Use custom `simulation/sim_logger.py` writing human-readable markdown files (per-tick, per-agent, per-oracle-call) to `logs/sim_<timestamp>/`.
- **Rejected alternatives**: structlog JSON lines (machine-parseable but hard to read during debugging), Python `logging` module (no structure).
- **Consequences**: Logs are not machine-parseable. Transition to structlog JSON is planned as a Phase 1 milestone once core behavior is stable.

### DEC-007: uv as package manager
- **Date**: 2026-02-28
- **Context**: Standard `pip`/`venv` workflow requires manual virtualenv management and doesn't provide a lock file by default.
- **Decision**: Use `uv` (not `pip`/`venv`) for all dependency management. Lock file via `uv.lock`. All execution via `uv run`.
- **Rejected alternatives**: `pip` + `venv` (slower installs, no lockfile), `poetry` (heavy), `conda` (overkill for this project).
- **Consequences**: All commands must be prefixed `uv run`. New runtime deps added via `uv add <pkg>`. Dev deps via `uv add --dev <pkg>`. `requirements.txt` is not used; `pyproject.toml` is the single source of truth.

### DEC-008: Behavioral audit system for prompt A/B testing
- **Date**: 2026-02-28
- **Context**: Iterating on agent prompts requires comparing behavioral outcomes across runs. Existing markdown logs are human-readable but not machine-parseable, making it impossible to quantify the effect of prompt changes.
- **Decision**: Add a lightweight audit system (`simulation/audit_recorder.py` + `simulation/audit_compare.py`) activated via `--audit` flag. Records structured JSONL events per agent-tick, prompt SHA-256 hashes in `meta.json`, and computed behavioral metrics in `summary.json`. A comparison CLI reads two runs and prints a 4-section terminal report (prompt diff, metrics table, behavioral fingerprint bars, stat sparklines).
- **Rejected alternatives**: structlog JSON (captures raw data but doesn't compute behavioral metrics), external analytics tools (adds dependencies), manual log reading (doesn't scale).
- **Consequences**: No new dependencies (stdlib only). Audit data written to `logs/sim_<timestamp>/audit/`. The `--audit` flag is opt-in so there's no performance impact on normal runs.

### DEC-009: Dual memory system (episodic + semantic)
- **Date**: 2026-03-02
- **Context**: Agents used a flat `list[str]` with 50-entry FIFO cap. Old knowledge was lost, preventing long-term pattern learning. By tick 60, agents had no memory of lessons from tick 5.
- **Decision**: Split memory into episodic (max 20, raw events) and semantic (max 30, compressed knowledge). Every 10 ticks the LLM compresses recent episodes into reusable lessons stored in semantic memory. Three-layer fallback on compression (null LLM, try/except, result validation). `add_memory()` signature preserved for backward compatibility; a `@property memory` shim handles direct access sites.
- **Rejected alternatives**: RAG with embeddings (too complex for Phase 1, requires vector DB), single memory with manual tagging (doesn't scale), persistent memory database (overengineering at this stage).
- **Consequences**: Agents can accumulate survival strategies over time. Prompt now shows `[KNOW]` and `[RECENT]` sections. Compression adds one LLM call per agent every 10 ticks. Memory class in `simulation/memory.py` is the single source of truth.

### DEC-010: Day/night cycle with 1 tick = 1 hour
- **Date**: 2026-03-03
- **Context**: Ticks had no semantic meaning beyond sequence number. Giving each tick a real-world duration grounds the simulation in human intuition, enables time-based survival mechanics, and sets up resource regeneration timing and weather for future phases.
- **Decision**: 1 tick = 1 in-world hour. 24-tick day split into 3 periods: day (hours 0–15, full vision, normal costs), sunset (hours 16–20, vision −1), night (hours 21–23, vision −2, energy action costs ×1.5). `DayCycle` class in `simulation/day_cycle.py` encapsulates all time logic. Start hour is configurable via `WORLD_START_HOUR = 6` (config) and `--start-hour` (CLI). `MAX_TICKS` bumped to 72 (3 full days). Time description injected into the agent decision prompt via `$time_info`.
- **Rejected alternatives**: 4-period cycle (dawn/day/dusk/night) — added complexity without proportional benefit at this stage; circadian sleep-debt mechanics — full sleep system deferred to Phase 2+; emergent-only (no mechanical effects, just tell agents the time) — no actual survival pressure without vision/energy changes; baking time logic into engine — violates single-responsibility.
- **Consequences**: `world.get_nearby_tiles()` receives a dynamic radius per tick (engine computes it). Oracle holds a `day_cycle` reference to scale energy costs on move/eat. Rest recovery is NOT multiplied (incentivises resting at night without penalising it). Resource regeneration timing (dawn-triggered) deferred to next PR.

### DEC-012: Automated devlog via /blog Claude Code skill
- **Date**: 2026-03-03
- **Context**: As features accumulated through PRs, there was no human-readable narrative of how the project evolved. Internal documentation (project-cornerstone/) covers design intent but not the lived experience of building it.
- **Decision**: Automated developer diary using a `/blog [PR-number]` Claude Code skill. The skill reads git diff, commit log, and relevant cornerstone context files, then generates a first-person English diary post in `blog/posts/YYYY-MM-DD-<slug>.md`. Post format: opening paragraph + 4 sections (What I built / Why it matters / Things to consider / What's next). Tone: diary-like, not a changelog. The skill is defined at `~/.claude/skills/blog/SKILL.md` and referenced in `CLAUDE.md` Quick Commands as a standard step after every PR.
- **Rejected alternatives**: GitHub Actions (no CI/CD yet; adds complexity), git hooks (only fires locally; fragile), fully automated (manual invocation preferred for quality control).
- **Consequences**: Running `/blog` after every PR is a project standard. Back-fill required for PRs #1–#11. Posts are Obsidian-compatible markdown, ready to serve with Quartz when desired.

### DEC-011: Structured innovation with prerequisites, effect bounds, and categories
- **Date**: 2026-03-03
- **Context**: Phase 0 innovation had no guardrails: agents could invent "build_house" with 5 energy on water, `ENERGY_COST_INNOVATE` was 0 (free spam), the LLM could return unbounded stat deltas (e.g. `hunger: -1000`), and there was no mechanism to detect redundant innovations.
- **Decision**: Four changes shipped together as Phase 1 structured innovation:
  1. **`requires` field** — optional dict in the innovate action JSON (`{"tile": "...", "min_energy": N}`). Oracle checks prerequisites before the LLM call; failure is immediate and free.
  2. **Effect bounds clamping** — `INNOVATION_EFFECT_BOUNDS` in `config.py` defines safe stat-delta ranges (hunger: −30/+10, energy: −20/+20, life: −15/+10). Applied by `Oracle._clamp_innovation_effects()` after every `_oracle_judge_custom_action()` call.
  3. **Category classification** — Oracle LLM now returns `"category": "SURVIVAL|CRAFTING|EXPLORATION|SOCIAL"` in the validation response. Stored in the innovation precedent, shown in the 🆕 log line.
  4. **Redundancy prevention via prompt** — existing action list passed to the validation LLM so it can reject semantically duplicate innovations. `ENERGY_COST_INNOVATE` raised from 0 → 10.
- **Rejected alternatives**: Keyword-based redundancy heuristics (too brittle — "gather_food" vs "forage" are the same concept but share no tokens); `nearby_resource` prerequisite (deferred to Phase 2 when inventory exists); material consumption (deferred to Phase 2).
- **Consequences**: `_validate_innovation()` prompt is longer (includes existing action list). Prerequisites fail silently before the LLM is consulted (no wasted calls). Effect clamping is applied at precedent-write time, so all future uses of the same cached result are also safe. `tests/test_innovation.py` covers all new paths with MockLLM.

## DEC-013 — Precedent Persistence Strategy

**Date:** 2026-03-04
**Decision:** Persist oracle precedents as `data/precedents_{seed}.json`. Auto-load on engine init, auto-save in `run()` / `run_with_callback()` finally blocks. Minimal JSON schema (version, seed, tick, precedents dict). No dataclass refactor (PrecedentKey/PrecedentValue deferred).
**Rationale:** Keeps runs deterministic across restarts and avoids redundant LLM calls for already-validated actions. Per-seed isolation prevents cross-contamination between different world configurations. Unseeded runs use `precedents_unseeded.json`. `save_precedents` does not raise (catches OSError/TypeError/ValueError) so a disk error in finally cannot mask a simulation exception.
**Alternatives considered:** Global single file (contamination risk across seeds); PrecedentKey/Value dataclasses (deferred — YAGNI until needed).

### DEC-014: Personality system deferred to Phase 3
- **Date**: 2026-03-05
- **Context**: Personality was the last pending item in Phase 1. Individual traits (courage, curiosity, patience) were designed to influence agent decision-making, but without other agents to interact with, the behavioral differences are minimal and hard to validate. The `sociability` trait was already scoped to Phase 3 in the design docs. Implementing the full personality system in Phase 2 would add complexity (prompt changes, config, dataclass, tests) with no social payoff until Phase 3.
- **Decision**: Move the personality system entirely to Phase 3. It will be designed alongside perception, communication, and social interaction mechanics. Sociability and individual traits will be introduced together when they can meaningfully affect agent behavior.
- **Rejected alternatives**: Implement individual traits only in Phase 1 and defer sociability to Phase 3 (split implementation adds fragmentation and maintenance cost across phases). Implement personality in Phase 2 (Phase 2 is survival-depth focused; personality doesn't affect resource gathering or crafting meaningfully).
- **Consequences**: Phase 1 is now complete. Phase 2 focuses entirely on survival depth (resources, inventory, crafting, weather). Phase 3 gains personality as its first item, making it the foundation for all social mechanics.

## DEC-015 — Resource Regeneration: Dawn-Triggered with Probability (2026-03-05)

**Context:** Trees deplete without regenerating, causing agents to starve mid-simulation.
This makes long-run testing of Phase 2 features (inventory, crafting) impractical.

**Decision:** At each dawn (`tick % DAY_LENGTH == 0`, skip tick 0), each depleted
tree tile has a 30% chance to regrow 1–3 fruit. Uses `World._rng = random.Random(seed)`,
a dedicated RNG instance seeded identically to world generation but independent of the
global `random` module.

**Alternatives considered:**
- Every-N-ticks (simpler): rejected — ignores the day/night system we just built.
- DayCycle event system: rejected — YAGNI; adds pub/sub complexity with no other subscribers.

**Constants:** `RESOURCE_REGEN_CHANCE=0.3`, `RESOURCE_REGEN_AMOUNT_MIN=1`, `RESOURCE_REGEN_AMOUNT_MAX=3`

**Files:** `simulation/config.py`, `simulation/world.py`, `simulation/engine.py`, `tests/test_world.py`

## DEC-016 — New Tile Types + Perlin Noise Generation

**Date:** 2026-03-05
**Status:** Implemented
**Files:** `simulation/world.py`, `simulation/oracle.py`, `simulation/config.py`, `simulation/engine.py`, `main.py`

### Decision
Add 5 new tile types (sand, forest, mountain, cave, river) and replace white-noise world generation with Perlin noise via the `opensimplex` library.

### Key choices

1. **All tiles walkable**: Even rivers. No tile is impassable except `water` (the existing deep water tile).
2. **Risk model**: River damage is Oracle-determined (LLM judges current strength, cached as precedent). Mountain has a hardcoded energy surcharge (`TILE_RISKS`). This separates "physics" (Oracle) from "configuration" (constants).
3. **Cave shelter**: Passive rest bonus (+20 energy) applied in `_resolve_rest()` via `TILE_REST_BONUS` config dict.
4. **New resources require innovation**: `mushroom`, `stone`, and `water` resources are not accessible via base actions. Only `fruit` works with `eat`. Agents must innovate `forage`, `mine`, `drink`, etc. — preserving the emergence-first philosophy.
5. **River water inexhaustible**: `consume_resource()` short-circuits for `type="water"` — never decrements, never deletes the river resource entry.
6. **World size configurable**: `--width` and `--height` CLI flags added to `main.py`, passed through `SimulationEngine` to `World`.
7. **Perlin two-pass**: Primary heightmap assigns biomes. Secondary river-noise map carves channels through sand/land zones.

### Alternatives considered
- Making rivers impassable (like water): rejected — user wanted all tiles walkable with emergent risk.
- Using Python's `noise` library: rejected — Python 3.12 compatibility issues; `opensimplex` chosen instead.
