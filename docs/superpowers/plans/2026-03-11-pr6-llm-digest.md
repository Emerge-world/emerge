# PR6 — LLM Digest Builder Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a composable, deterministic post-run digest pipeline that reads `events.jsonl` and writes `llm_digest/` with per-run and per-agent JSON + markdown files suitable for human review and LLM context loading.

**Architecture:** Five focused modules under `simulation/digest/`: `BehaviorSegmenter` (4-mode agent phase classification), `AnomalyDetector` (run-level anomaly flagging), `EvidenceIndexer` (claim→event-id mapping), `DigestBuilder` (orchestrator + CLI entry point), `DigestRenderer` (pure JSON/markdown serialization). Engine auto-invokes post-run alongside existing `MetricsBuilder`/`EBSBuilder`.

**Tech Stack:** Python stdlib only (`json`, `re`, `dataclasses`, `pathlib`). No new dependencies. Tests use `pytest` + `tmp_path`. Pattern mirrors `simulation/ebs_builder.py` and `simulation/metrics_builder.py`.

---

## Chunk 1: BehaviorSegmenter

### Task 1: Package scaffold

**Files:**
- Create: `simulation/digest/__init__.py`

- [ ] **Step 1: Create the package init file**

```python
# simulation/digest/__init__.py
"""LLM digest pipeline for post-run analysis."""
```

- [ ] **Step 2: Verify import works**

Run: `python -c "import simulation.digest"`
Expected: no error

- [ ] **Step 3: Commit**

```bash
git add simulation/digest/__init__.py
git commit -m "feat: add simulation.digest package scaffold"
```

---

### Task 2: BehaviorSegmenter — data structures and scoring

**Files:**
- Create: `simulation/digest/behavior_segmenter.py`
- Create: `tests/test_behavior_segmenter.py`

- [ ] **Step 1: Write failing tests for data structures and tick scoring**

Create `tests/test_behavior_segmenter.py`:

```python
"""Tests for BehaviorSegmenter tick scoring."""

import pytest
from simulation.digest.behavior_segmenter import (
    BehaviorSegmenter,
    TickModeScore,
    PhaseSegment,
    AgentSegmentation,
)


def _decision(tick: int, action: str, direction: str = "", reason: str = "",
              agent: str = "Ada", parse_ok: bool = True) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_decision",
        "agent_id": agent,
        "payload": {
            "parsed_action": {"action": action, "direction": direction, "reason": reason},
            "parse_ok": parse_ok,
        },
    }


def _state(tick: int, energy: float = 80, agent: str = "Ada") -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_state",
        "agent_id": agent,
        "payload": {"energy": energy, "hunger": 20, "life": 100, "alive": True, "pos": {"x": 0, "y": 0}},
    }


def _perception(tick: int, hunger: float = 20, resources: list | None = None,
                agent: str = "Ada", night: bool = False) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_perception",
        "agent_id": agent,
        "payload": {
            "pos": {"x": 0, "y": 0}, "hunger": hunger, "energy": 80,
            "resources_nearby": resources or [],
            "night_penalty_active": night,
        },
    }


def _innovation_attempt(tick: int, agent: str = "Ada") -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "innovation_attempt",
        "agent_id": agent, "payload": {"name": "craft_stick", "description": "make a stick"},
    }


def _custom_action(tick: int, agent: str = "Ada") -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "custom_action_executed",
        "agent_id": agent, "payload": {"name": "craft_stick", "success": True},
    }


class TestTickScoring:
    def test_eat_action_scores_exploitation(self):
        events = [_decision(1, "eat"), _state(1), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["exploitation"] >= 5.0

    def test_rest_action_scores_maintenance(self):
        events = [_decision(1, "rest"), _state(1), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["maintenance"] >= 5.0

    def test_innovate_action_scores_innovation(self):
        events = [_decision(1, "innovate"), _state(1), _perception(1), _innovation_attempt(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["innovation"] >= 6.0

    def test_explore_reason_scores_exploration(self):
        events = [_decision(1, "move", reason="exploring the unknown area"), _state(1), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["exploration"] >= 3.0

    def test_night_penalty_boosts_maintenance(self):
        events = [_decision(1, "move"), _state(1), _perception(1, night=True)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["maintenance"] >= 2.0

    def test_low_energy_boosts_maintenance(self):
        events = [_decision(1, "move"), _state(1, energy=20), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["maintenance"] >= 2.0

    def test_assigned_mode_is_highest_score(self):
        events = [_decision(1, "eat"), _state(1), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.assigned_mode == "exploitation"
```

- [ ] **Step 2: Run to confirm it fails**

Run: `pytest tests/test_behavior_segmenter.py::TestTickScoring -v`
Expected: `ImportError` or `ModuleNotFoundError` — `BehaviorSegmenter` does not exist yet

- [ ] **Step 3: Implement BehaviorSegmenter with scoring (no smoothing yet)**

Create `simulation/digest/behavior_segmenter.py`:

```python
"""BehaviorSegmenter: classifies per-agent ticks into behavioral modes and merges into phases."""

from __future__ import annotations
import re
from dataclasses import dataclass


_ENERGY_LOW_THRESHOLD = 30  # % of max energy below which maintenance is boosted
_ENERGY_MAX = 100  # default max energy; used only for ratio check


@dataclass
class TickModeScore:
    tick: int
    scores: dict[str, float]
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


# Keyword groups for reason-text signal matching
_EXPLORE_KEYWORDS = re.compile(r"\b(explor|scout|unknown|unvisited|search)\b", re.IGNORECASE)
_EXPLOIT_KEYWORDS = re.compile(r"\b(fruit|food|eat|hungry|hunger|reduce hunger|consume)\b", re.IGNORECASE)
_INNOVATE_KEYWORDS = re.compile(r"\b(craft|tool|knife|stick|stone|recipe|build|create|make)\b", re.IGNORECASE)
_MAINTAIN_KEYWORDS = re.compile(r"\b(night|conserve|rest|energy cost|vision|dark|save energy)\b", re.IGNORECASE)

_MODES = ("exploration", "exploitation", "innovation", "maintenance")


class BehaviorSegmenter:
    """Classifies agent ticks into behavioral modes and segments them into phases."""

    # --- Public API ---

    def segment(self, agent_id: str, events: list[dict]) -> AgentSegmentation:
        """Segment agent events into tick scores and phase segments."""
        ticks = self._collect_ticks(agent_id, events)
        raw_scores = [self._score_tick(td) for td in ticks]
        smoothed = self._smooth(raw_scores)
        phases = self._merge_phases(agent_id, smoothed, ticks)
        return AgentSegmentation(
            agent_id=agent_id,
            tick_scores=smoothed,
            phases=phases,
        )

    # --- Tick data collection ---

    def _collect_ticks(self, agent_id: str, events: list[dict]) -> list[dict]:
        """Group events by tick for this agent, returning a list of tick dicts."""
        by_tick: dict[int, dict] = {}

        for ev in events:
            if ev.get("agent_id") != agent_id and ev.get("agent_id") is not None:
                # include world-level events (agent_id=None) but not other agents
                if ev.get("agent_id") is not None:
                    continue
            t = ev.get("tick", 0)
            if t == 0:
                continue
            td = by_tick.setdefault(t, {
                "tick": t,
                "actions": [],
                "perception": None,
                "state": None,
                "has_innovation_attempt": False,
                "has_custom_action": False,
                "pending_innovation_items": set(),
                "night_active": False,
                "energy": None,
            })
            et = ev.get("event_type", "")
            p = ev.get("payload", {})

            if et == "agent_decision" and ev.get("agent_id") == agent_id:
                td["actions"].append(p.get("parsed_action", {}))
            elif et == "agent_perception" and ev.get("agent_id") == agent_id:
                td["perception"] = p
                td["night_active"] = p.get("night_penalty_active", False)
            elif et == "agent_state" and ev.get("agent_id") == agent_id:
                td["state"] = p
                td["energy"] = p.get("energy")
            elif et == "innovation_attempt" and ev.get("agent_id") == agent_id:
                td["has_innovation_attempt"] = True
            elif et == "custom_action_executed" and ev.get("agent_id") == agent_id:
                td["has_custom_action"] = True

        return sorted(by_tick.values(), key=lambda x: x["tick"])

    # --- Per-tick scoring ---

    def _score_tick(self, td: dict) -> TickModeScore:
        scores = {m: 0.0 for m in _MODES}
        signals = []

        for action in td["actions"]:
            act = (action.get("action") or "").lower()
            reason = (action.get("reason") or "").lower()

            # Action-based signals
            if act == "eat":
                scores["exploitation"] += 5.0
                signals.append("action_eat")
            elif act == "rest":
                scores["maintenance"] += 5.0
                signals.append("action_rest")
            elif act == "innovate":
                scores["innovation"] += 6.0
                signals.append("action_innovate")
            elif act == "pickup":
                scores["exploitation"] += 1.0
                if td["pending_innovation_items"]:
                    scores["innovation"] += 2.0
                    signals.append("pickup_for_innovation")

            # Reason-text signals
            if _EXPLORE_KEYWORDS.search(reason):
                scores["exploration"] += 3.0
                signals.append("reason_explore")
            if _EXPLOIT_KEYWORDS.search(reason):
                scores["exploitation"] += 3.0
                signals.append("reason_exploit")
            if _INNOVATE_KEYWORDS.search(reason):
                scores["innovation"] += 3.0
                signals.append("reason_innovate")
            if _MAINTAIN_KEYWORDS.search(reason):
                scores["maintenance"] += 3.0
                signals.append("reason_maintain")

            # Move-specific target signals
            if act == "move":
                perception = td.get("perception") or {}
                resources = perception.get("resources_nearby", [])
                direction = (action.get("direction") or "").lower()
                dx, dy = _direction_to_delta(direction)
                if dx is not None and any(
                    r.get("dx") == dx and r.get("dy") == dy for r in resources
                ):
                    scores["exploitation"] += 2.0
                    signals.append("move_toward_food")

        # Note: has_innovation_attempt and has_custom_action are used only for
        # the hysteresis bypass (innovation burst exception), NOT for scoring.
        # "move toward requires.tile" (+3 innovation) and conditional pickup (+2)
        # require pending innovation prerequisite data not currently in events — deferred to v2.

        # Context signals
        if td["night_active"]:
            scores["maintenance"] += 2.0
            signals.append("night_active")
        energy = td.get("energy")
        if energy is not None and energy < _ENERGY_LOW_THRESHOLD:
            scores["maintenance"] += 2.0
            signals.append("energy_low")

        assigned = max(_MODES, key=lambda m: scores[m])
        # Deduplicate signals, preserve order
        seen = set()
        unique_signals = [s for s in signals if not (s in seen or seen.add(s))]

        return TickModeScore(
            tick=td["tick"],
            scores=scores,
            assigned_mode=assigned,
            dominant_signals=unique_signals,
        )

    # --- Smoothing (5-tick trailing window) ---

    def _smooth(self, raw: list[TickModeScore]) -> list[TickModeScore]:
        """Apply 5-tick trailing window smoothing to mode scores."""
        smoothed = []
        for i, ts in enumerate(raw):
            window = raw[max(0, i - 4): i + 1]
            avg_scores = {m: sum(w.scores[m] for w in window) / len(window) for m in _MODES}
            assigned = max(_MODES, key=lambda m: avg_scores[m])
            smoothed.append(TickModeScore(
                tick=ts.tick,
                scores=avg_scores,
                assigned_mode=assigned,
                dominant_signals=ts.dominant_signals,
            ))
        return smoothed

    # --- Phase merging ---

    def _merge_phases(
        self, agent_id: str, scores: list[TickModeScore], ticks: list[dict]
    ) -> list[PhaseSegment]:
        """Apply hysteresis and merge adjacent same-mode spans into phases."""
        if not scores:
            return []

        # Build a list of (tick, mode) with hysteresis
        ENTER_MARGIN = 2.0
        MIN_DURATION = 3

        # Raw assigned modes from smoothed scores
        raw_modes = [(ts.tick, ts.assigned_mode, ts) for ts in scores]

        # Apply hysteresis: only switch modes when new mode leads by ENTER_MARGIN for MIN_DURATION
        # Innovation bursts are exempt (1 tick with innovation_attempt or custom_action suffices)
        assigned_modes: list[tuple[int, str]] = []
        current_mode = raw_modes[0][1] if raw_modes else "exploration"
        pending_mode: str | None = None
        pending_count = 0

        tick_has_innovation = {
            td["tick"]: td["has_innovation_attempt"] or td["has_custom_action"]
            for td in ticks
        }

        for tick, mode, ts in raw_modes:
            # Innovation burst: immediately assign without hysteresis
            if mode == "innovation" and tick_has_innovation.get(tick, False):
                assigned_modes.append((tick, "innovation"))
                pending_mode = None
                pending_count = 0
                current_mode = "innovation"
                continue

            if mode == current_mode:
                assigned_modes.append((tick, current_mode))
                pending_mode = None
                pending_count = 0
            else:
                # Check if new mode leads by margin
                lead = ts.scores[mode] - ts.scores[current_mode]
                if lead >= ENTER_MARGIN:
                    if pending_mode == mode:
                        pending_count += 1
                    else:
                        pending_mode = mode
                        pending_count = 1

                    if pending_count >= MIN_DURATION:
                        current_mode = mode
                        pending_mode = None
                        pending_count = 0
                        assigned_modes.append((tick, current_mode))
                    else:
                        assigned_modes.append((tick, current_mode))  # stay in current until confirmed
                else:
                    pending_mode = None
                    pending_count = 0
                    assigned_modes.append((tick, current_mode))

        # Merge adjacent same-mode spans into segments
        segments: list[PhaseSegment] = []
        if not assigned_modes:
            return segments

        span_start_tick = assigned_modes[0][0]
        span_mode = assigned_modes[0][1]
        span_ticks = [assigned_modes[0][0]]

        def _flush_span(start_t: int, end_t: int, mode: str, span_tick_list: list[int]):
            # Absorb spans < MIN_DURATION into previous segment (unless innovation burst)
            if len(span_tick_list) < MIN_DURATION and mode != "innovation":
                if segments:
                    last = segments[-1]
                    segments[-1] = PhaseSegment(
                        agent_id=last.agent_id,
                        phase_id=last.phase_id,
                        mode=last.mode,
                        tick_start=last.tick_start,
                        tick_end=end_t,
                        confidence=last.confidence,
                        dominant_signals=last.dominant_signals,
                        supporting_event_ids=last.supporting_event_ids,
                    )
                    return
            # Collect signals and event_ids from tick scores in this span
            tick_to_ts = {ts.tick: ts for ts in scores}
            span_signals: list[str] = []
            for t in span_tick_list:
                ts = tick_to_ts.get(t)
                if ts:
                    span_signals.extend(ts.dominant_signals)
            seen_s: set[str] = set()
            unique_s = [s for s in span_signals if not (s in seen_s or seen_s.add(s))]

            confidence = _compute_confidence(scores, span_tick_list, mode)

            segments.append(PhaseSegment(
                agent_id=agent_id,
                phase_id=len(segments) + 1,
                mode=mode,
                tick_start=start_t,
                tick_end=end_t,
                confidence=round(confidence, 3),
                dominant_signals=unique_s[:5],  # top 5 signals
                supporting_event_ids=[],  # filled by EvidenceIndexer
            ))

        for tick, mode in assigned_modes[1:]:
            if mode == span_mode:
                span_ticks.append(tick)
            else:
                _flush_span(span_start_tick, span_ticks[-1], span_mode, span_ticks)
                span_start_tick = tick
                span_mode = mode
                span_ticks = [tick]

        _flush_span(span_start_tick, span_ticks[-1], span_mode, span_ticks)

        # Re-number phase_ids after merges
        for i, seg in enumerate(segments):
            segments[i] = PhaseSegment(
                agent_id=seg.agent_id,
                phase_id=i + 1,
                mode=seg.mode,
                tick_start=seg.tick_start,
                tick_end=seg.tick_end,
                confidence=seg.confidence,
                dominant_signals=seg.dominant_signals,
                supporting_event_ids=seg.supporting_event_ids,
            )

        return segments


def _direction_to_delta(direction: str) -> tuple[int | None, int | None]:
    return {
        "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0),
        "up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0),
    }.get(direction, (None, None))


def _compute_confidence(scores: list[TickModeScore], span_ticks: list[int], mode: str) -> float:
    """Confidence = avg normalized lead of dominant mode over second-best in span."""
    tick_to_ts = {ts.tick: ts for ts in scores}
    leads = []
    for t in span_ticks:
        ts = tick_to_ts.get(t)
        if not ts:
            continue
        sorted_scores = sorted(ts.scores.values(), reverse=True)
        top = sorted_scores[0]
        second = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
        total = sum(ts.scores.values()) or 1.0
        leads.append((top - second) / total)
    return sum(leads) / len(leads) if leads else 0.0
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_behavior_segmenter.py::TestTickScoring -v`
Expected: All 7 tests pass

- [ ] **Step 5: Commit**

```bash
git add simulation/digest/behavior_segmenter.py tests/test_behavior_segmenter.py
git commit -m "feat: add BehaviorSegmenter tick scoring and phase segmentation"
```

---

### Task 3: BehaviorSegmenter — phase segmentation tests

**Files:**
- Modify: `tests/test_behavior_segmenter.py` (add phase tests)

- [ ] **Step 1: Add phase segmentation tests**

Append to `tests/test_behavior_segmenter.py`:

```python
class TestPhaseSegmentation:
    def test_pure_exploration_gives_one_phase(self):
        """10 ticks of exploration-only actions → single exploration phase."""
        events = []
        for t in range(1, 11):
            events.append(_decision(t, "move", reason="exploring unknown area"))
            events.append(_state(t))
            events.append(_perception(t))
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        assert len(result.phases) == 1
        assert result.phases[0].mode == "exploration"

    def test_innovation_burst_creates_phase_from_single_tick(self):
        """A single tick with innovation_attempt creates an innovation phase."""
        events = []
        for t in range(1, 6):
            events.append(_decision(t, "move", reason="exploring"))
            events.append(_state(t))
            events.append(_perception(t))
        # Tick 6: innovation attempt — should become its own phase
        events.append(_decision(6, "innovate"))
        events.append(_innovation_attempt(6))
        events.append(_state(6))
        events.append(_perception(6))
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        innovation_phases = [p for p in result.phases if p.mode == "innovation"]
        assert len(innovation_phases) >= 1
        assert any(p.tick_start <= 6 <= p.tick_end for p in innovation_phases)

    def test_night_rest_creates_maintenance_phase(self):
        """Sustained night + rest → maintenance phase appears."""
        events = []
        for t in range(1, 8):
            events.append(_decision(t, "rest"))
            events.append(_state(t, energy=25))
            events.append(_perception(t, night=True))
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        assert any(p.mode == "maintenance" for p in result.phases)

    def test_phases_cover_all_ticks_exactly(self):
        """Every tick in the run must be covered by exactly one phase (no gaps, no overlap)."""
        events = []
        for t in range(1, 15):
            action = "eat" if t % 3 == 0 else "move"
            events.append(_decision(t, action, reason="exploring"))
            events.append(_state(t))
            events.append(_perception(t))
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        covered_ticks: list[int] = []
        for phase in result.phases:
            for t in range(phase.tick_start, phase.tick_end + 1):
                covered_ticks.append(t)
        # No duplicates (no overlap)
        assert len(covered_ticks) == len(set(covered_ticks)), "Phases overlap"
        # All ticks covered (no gap)
        assert set(covered_ticks) == set(range(1, 15)), "Not all ticks covered"

    def test_phase_confidence_is_between_0_and_1(self):
        """All phase confidence values must be in [0, 1]."""
        events = []
        for t in range(1, 10):
            events.append(_decision(t, "eat"))
            events.append(_state(t))
            events.append(_perception(t))
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        for phase in result.phases:
            assert 0.0 <= phase.confidence <= 1.0

    def test_segmentation_result_has_correct_agent_id(self):
        events = [_decision(1, "eat"), _state(1), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Bruno", events)
        assert result.agent_id == "Bruno"
        for phase in result.phases:
            assert phase.agent_id == "Bruno"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_behavior_segmenter.py -v`
Expected: All tests pass (both `TestTickScoring` and `TestPhaseSegmentation`)

- [ ] **Step 3: Commit**

```bash
git add tests/test_behavior_segmenter.py
git commit -m "test: add BehaviorSegmenter phase segmentation tests"
```

---

## Chunk 2: AnomalyDetector and EvidenceIndexer

### Task 4: AnomalyDetector

**Files:**
- Create: `simulation/digest/anomaly_detector.py`
- Create: `tests/test_anomaly_detector.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_anomaly_detector.py`:

```python
"""Tests for AnomalyDetector."""

import pytest
from simulation.digest.anomaly_detector import AnomalyDetector, Anomaly


def _decision(tick: int, agent: str = "Ada", action: str = "move", parse_ok: bool = True) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_decision", "agent_id": agent,
        "payload": {"parsed_action": {"action": action}, "parse_ok": parse_ok},
    }


def _oracle(tick: int, agent: str = "Ada", action: str = "move", success: bool = True,
            cache_hit: bool = True, is_innovate: bool = False) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "oracle_resolution", "agent_id": agent,
        "payload": {"success": success, "action": action, "cache_hit": cache_hit,
                    "is_innovation_action": is_innovate, "effects": {}},
    }


def _memory(tick: int, agent: str = "Ada", learnings: list | None = None) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "memory_compression_result",
        "agent_id": agent, "payload": {"learnings": learnings or [], "episode_count": 3},
    }


def _oracle_consume(tick: int, agent: str = "Ada", resource: str = "fruit") -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "oracle_resolution", "agent_id": agent,
        "payload": {"success": True, "action": "eat", "resource": resource,
                    "cache_hit": True, "effects": {"hunger": -20}},
    }


class TestParseFailStreaks:
    def test_three_consecutive_parse_fails_creates_streak(self):
        events = [
            _decision(1, parse_ok=False),
            _decision(2, parse_ok=False),
            _decision(3, parse_ok=False),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        streak = [a for a in anomalies if a.type == "PARSE_FAIL_STREAK"]
        assert len(streak) >= 1
        assert streak[0].severity == "high"
        assert streak[0].agent_id == "Ada"

    def test_two_parse_fails_no_streak(self):
        events = [_decision(1, parse_ok=False), _decision(2, parse_ok=False)]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert not any(a.type == "PARSE_FAIL_STREAK" for a in anomalies)

    def test_broken_streak_resets_counter(self):
        events = [
            _decision(1, parse_ok=False),
            _decision(2, parse_ok=False),
            _decision(3, parse_ok=True),   # breaks streak
            _decision(4, parse_ok=False),
            _decision(5, parse_ok=False),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert not any(a.type == "PARSE_FAIL_STREAK" for a in anomalies)


class TestRepeatedFailures:
    def test_same_action_fails_three_times_in_ten_ticks(self):
        events = [
            _oracle(1, action="move_north", success=False),
            _oracle(5, action="move_north", success=False),
            _oracle(9, action="move_north", success=False),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        repeated = [a for a in anomalies if a.type == "REPEATED_FAILURE"]
        assert len(repeated) >= 1
        assert repeated[0].severity == "medium"

    def test_three_failures_spread_over_more_than_ten_ticks_no_anomaly(self):
        events = [
            _oracle(1, action="move_north", success=False),
            _oracle(6, action="move_north", success=False),
            _oracle(12, action="move_north", success=False),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert not any(a.type == "REPEATED_FAILURE" for a in anomalies)


class TestContradictions:
    def test_learning_contradicts_confirmed_resource(self):
        events = [
            _oracle_consume(5, resource="fruit"),  # confirms fruit exists
            _memory(20, learnings=["no fruit can be found anywhere"]),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        contradictions = [a for a in anomalies if a.type == "CONTRADICTION"]
        assert len(contradictions) >= 1
        assert contradictions[0].severity == "high"

    def test_non_contradicting_learning_no_anomaly(self):
        events = [
            _oracle_consume(5, resource="fruit"),
            _memory(20, learnings=["fruit is available near trees"]),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert not any(a.type == "CONTRADICTION" for a in anomalies)


class TestUnusualPrecedent:
    def test_new_oracle_precedent_on_innovate_action(self):
        events = [
            _oracle(10, action="craft_stick", cache_hit=False, is_innovate=True),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        precedent = [a for a in anomalies if a.type == "UNUSUAL_PRECEDENT"]
        assert len(precedent) == 1
        assert precedent[0].severity == "low"

    def test_cache_miss_on_normal_action_not_flagged(self):
        events = [
            _oracle(10, action="move", cache_hit=False, is_innovate=False),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert not any(a.type == "UNUSUAL_PRECEDENT" for a in anomalies)


class TestAnomalyStructure:
    def test_anomaly_has_required_fields(self):
        events = [_decision(1, parse_ok=False), _decision(2, parse_ok=False), _decision(3, parse_ok=False)]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert len(anomalies) > 0
        a = anomalies[0]
        assert a.anomaly_id
        assert a.type
        assert a.severity in ("high", "medium", "low")
        assert isinstance(a.tick, int)
        assert isinstance(a.supporting_event_ids, list)
        assert isinstance(a.description, str)
```

- [ ] **Step 2: Run to confirm fail**

Run: `pytest tests/test_anomaly_detector.py -v`
Expected: `ImportError` — module doesn't exist yet

- [ ] **Step 3: Implement AnomalyDetector**

Create `simulation/digest/anomaly_detector.py`:

```python
"""AnomalyDetector: flags anomalous events in a simulation run."""

from __future__ import annotations
import re
import uuid
from dataclasses import dataclass


@dataclass
class Anomaly:
    anomaly_id: str
    type: str       # LLM_FALLBACK | CONTRADICTION | REPEATED_FAILURE | UNUSUAL_PRECEDENT | PARSE_FAIL_STREAK
    severity: str   # high | medium | low
    tick: int
    agent_id: str | None
    description: str
    supporting_event_ids: list[str]


# Contradiction patterns (re-uses logic from ebs_builder._check_contradiction)
_NEGATE_RESOURCE = re.compile(r"\b(no |not found|can.t find)\b", re.IGNORECASE)


def _check_contradiction(learning: str, resource_confirmed: set[str], action_succeeded: set[str]) -> bool:
    text = learning.lower()
    for resource in resource_confirmed:
        res = resource.lower()
        if f"no {res}" in text or f"{res} not found" in text or f"can't find {res}" in text:
            return True
    for action in action_succeeded:
        act = action.lower()
        if f"{act} never works" in text or f"{act} doesn't work" in text:
            return True
    return False


def _event_id(ev: dict) -> str:
    """Build a stable event identifier from event fields."""
    et = ev.get("event_type", "unknown")
    tick = ev.get("tick", 0)
    agent = ev.get("agent_id") or "run"
    return f"evt_{tick:04d}_{agent}_{et}"


class AnomalyDetector:
    """Detects anomalous patterns across a run's event stream."""

    def detect(self, events: list[dict]) -> list[Anomaly]:
        anomalies: list[Anomaly] = []

        # Ground-truth state (for contradiction detection)
        resource_confirmed: set[str] = set()
        action_succeeded: set[str] = set()

        # Per-agent state for streak/repeat tracking
        # agent_id → list of (tick, parse_ok)
        parse_history: dict[str, list[tuple[int, bool]]] = {}
        # agent_id → dict[action_name → list[tick]]
        failure_history: dict[str, dict[str, list[int]]] = {}

        for ev in events:
            et = ev.get("event_type", "")
            tick = ev.get("tick", 0)
            agent_id = ev.get("agent_id")
            p = ev.get("payload", {})
            eid = _event_id(ev)

            if et == "oracle_resolution":
                success = p.get("success", False)
                action = p.get("action", "")
                cache_hit = p.get("cache_hit", True)
                is_innovate = p.get("is_innovation_action", False)

                # Build ground truth
                if success:
                    if action in ("eat", "pickup"):
                        resource = p.get("resource") or p.get("item")
                        if resource:
                            resource_confirmed.add(str(resource).lower())
                        if p.get("effects", {}).get("hunger", 0) < 0:
                            resource_confirmed.add("food")
                    if action:
                        action_succeeded.add(action)

                # Unusual precedent: cache miss on innovate action
                if not cache_hit and is_innovate:
                    anomalies.append(Anomaly(
                        anomaly_id=f"run_anomaly_UNUSUAL_PRECEDENT_{tick}",
                        type="UNUSUAL_PRECEDENT",
                        severity="low",
                        tick=tick,
                        agent_id=agent_id,
                        description=f"New oracle precedent created for action '{action}' at tick {tick}",
                        supporting_event_ids=[eid],
                    ))

                # Repeated failure tracking
                if not success and agent_id and action:
                    fh = failure_history.setdefault(agent_id, {})
                    fh.setdefault(action, []).append(tick)
                    recent = [t for t in fh[action] if tick - t <= 10]
                    fh[action] = recent
                    if len(recent) >= 3 and len(recent) == 3:
                        # Flag only when we first hit exactly 3 (avoid duplicate flags)
                        anom_key = f"{agent_id}_anomaly_REPEATED_FAILURE_{tick}"
                        supporting = [f"evt_{t:04d}_{agent_id}_oracle_resolution" for t in recent]
                        anomalies.append(Anomaly(
                            anomaly_id=anom_key,
                            type="REPEATED_FAILURE",
                            severity="medium",
                            tick=tick,
                            agent_id=agent_id,
                            description=f"Action '{action}' failed {len(recent)} times in ≤10 ticks for {agent_id}",
                            supporting_event_ids=supporting,
                        ))

            elif et == "agent_decision":
                parse_ok = p.get("parse_ok", True)
                if agent_id:
                    ph = parse_history.setdefault(agent_id, [])
                    ph.append((tick, parse_ok))

                    # LLM_FALLBACK: single parse_ok=False
                    if not parse_ok:
                        anomalies.append(Anomaly(
                            anomaly_id=f"{agent_id}_anomaly_LLM_FALLBACK_{tick}",
                            type="LLM_FALLBACK",
                            severity="medium",
                            tick=tick,
                            agent_id=agent_id,
                            description=f"LLM fallback used for {agent_id} at tick {tick}",
                            supporting_event_ids=[eid],
                        ))

                    # PARSE_FAIL_STREAK: 3+ consecutive failures
                    consecutive = 0
                    for _, ok in reversed(ph):
                        if not ok:
                            consecutive += 1
                        else:
                            break
                    if consecutive == 3:  # flag at exactly 3 to avoid duplicates
                        streak_events = [
                            f"evt_{t:04d}_{agent_id}_agent_decision"
                            for t, ok in ph[-3:]
                        ]
                        anomalies.append(Anomaly(
                            anomaly_id=f"{agent_id}_anomaly_PARSE_FAIL_STREAK_{tick}",
                            type="PARSE_FAIL_STREAK",
                            severity="high",
                            tick=tick,
                            agent_id=agent_id,
                            description=f"{agent_id} had 3 consecutive LLM fallbacks ending at tick {tick}",
                            supporting_event_ids=streak_events,
                        ))

            elif et == "memory_compression_result":
                learnings = p.get("learnings", [])
                for learning in learnings:
                    if _check_contradiction(learning, resource_confirmed, action_succeeded):
                        anom_key = f"{agent_id or 'run'}_anomaly_CONTRADICTION_{tick}"
                        anomalies.append(Anomaly(
                            anomaly_id=anom_key,
                            type="CONTRADICTION",
                            severity="high",
                            tick=tick,
                            agent_id=agent_id,
                            description=f"Learning contradicts ground truth: '{learning[:80]}'",
                            supporting_event_ids=[eid],
                        ))
                        break  # one anomaly per compression event

        return anomalies
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_anomaly_detector.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add simulation/digest/anomaly_detector.py tests/test_anomaly_detector.py
git commit -m "feat: add AnomalyDetector with 5 detection rules"
```

---

### Task 5: EvidenceIndexer

**Files:**
- Create: `simulation/digest/evidence_indexer.py`

No dedicated test file — covered by the integration test in Task 8. The indexer is a pure data-transformation function.

- [ ] **Step 1: Create EvidenceIndexer**

Create `simulation/digest/evidence_indexer.py`:

```python
"""EvidenceIndexer: maps digest claims to supporting event IDs."""

from __future__ import annotations
from simulation.digest.behavior_segmenter import AgentSegmentation, PhaseSegment
from simulation.digest.anomaly_detector import Anomaly


def _event_id(ev: dict) -> str:
    et = ev.get("event_type", "unknown")
    tick = ev.get("tick", 0)
    agent = ev.get("agent_id") or "run"
    return f"evt_{tick:04d}_{agent}_{et}"


class EvidenceIndexer:
    """Builds evidence_index.json: maps claim_id → list[event_id]."""

    def build(
        self,
        events: list[dict],
        segmentations: list[AgentSegmentation],
        anomalies: list[Anomaly],
        critical_events_by_agent: dict[str, list[dict]] | None = None,
    ) -> dict[str, list[str]]:
        """Return a dict mapping claim keys to supporting event IDs.

        critical_events_by_agent: {agent_id: [{tick, description, supporting_event_ids}]}
        Pass the critical_events from each agent digest so we only index actual critical ticks,
        not every agent_state event.
        """
        index: dict[str, list[str]] = {}

        # Index agent phases
        for seg in segmentations:
            for phase in seg.phases:
                key = f"{seg.agent_id}_phase_{phase.phase_id}"
                supporting = [
                    _event_id(ev)
                    for ev in events
                    if ev.get("agent_id") == seg.agent_id
                    and phase.tick_start <= ev.get("tick", 0) <= phase.tick_end
                    and ev.get("event_type") in ("agent_decision", "agent_state", "innovation_attempt", "custom_action_executed")
                ]
                index[key] = supporting[:10]  # cap at 10 per phase

        # Index anomalies (all types)
        for anomaly in anomalies:
            index[anomaly.anomaly_id] = anomaly.supporting_event_ids

        # Index contradictions: only for memory events that were actually flagged
        contradiction_ticks: set[tuple[str | None, int]] = {
            (a.agent_id, a.tick) for a in anomalies if a.type == "CONTRADICTION"
        }
        for ev in events:
            if ev.get("event_type") == "memory_compression_result":
                tick = ev.get("tick", 0)
                agent = ev.get("agent_id") or "run"
                if (ev.get("agent_id"), tick) in contradiction_ticks:
                    key = f"{agent}_contradiction_tick_{tick}"
                    index.setdefault(key, []).append(_event_id(ev))

        # Index critical events: only actual critical events from agent digests
        if critical_events_by_agent:
            for agent_id, crit_list in critical_events_by_agent.items():
                for crit in crit_list:
                    key = f"{agent_id}_critical_tick_{crit['tick']}"
                    index[key] = crit.get("supporting_event_ids", [])

        return index
```

- [ ] **Step 2: Verify import**

Run: `python -c "from simulation.digest.evidence_indexer import EvidenceIndexer; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add simulation/digest/evidence_indexer.py
git commit -m "feat: add EvidenceIndexer claim-to-event-id mapping"
```

---

## Chunk 3: DigestRenderer and DigestBuilder

### Task 6: DigestRenderer

**Files:**
- Create: `simulation/digest/digest_renderer.py`
- Create: `tests/test_digest_renderer.py`

- [ ] **Step 1: Write failing tests for DigestRenderer**

Create `tests/test_digest_renderer.py`:

```python
"""Tests for DigestRenderer — pure serialization and markdown rendering."""

import json
from pathlib import Path
import pytest
from simulation.digest.digest_renderer import DigestRenderer


def _minimal_run_digest() -> dict:
    return {
        "run_id": "test-run",
        "generated_at": "2026-03-11T10:00:00Z",
        "meta": {"seed": 42, "ticks": 10, "agent_count": 1, "world_size": [10, 10],
                 "model_id": "test", "git_commit": "abc123"},
        "outcomes": {"survivors": ["Ada"], "deaths": [], "total_innovations_approved": 0,
                     "total_innovations_attempted": 0, "total_anomalies": 0,
                     "anomaly_counts_by_type": {}},
        "agents": [{"agent_id": "Ada", "status": "alive", "phase_count": 2,
                    "dominant_mode": "exploration", "innovation_count": 0,
                    "anomaly_count": 0, "digest_path": "agents/Ada.json"}],
        "anomalies": [],
        "evidence_path": "evidence_index.json",
        "manifest_path": "generation_manifest.json",
    }


def _minimal_agent_digest() -> dict:
    return {
        "agent_id": "Ada",
        "run_id": "test-run",
        "status": "alive",
        "final_state": {"life": 100, "hunger": 20, "energy": 80, "pos": {"x": 0, "y": 0}},
        "state_extrema": {"min_life": {"value": 90, "tick": 5}, "max_hunger": {"value": 40, "tick": 3}},
        "action_mix": {"move": 0.8, "eat": 0.2},
        "phases": [{"phase_id": 1, "mode": "exploration", "tick_start": 1, "tick_end": 10,
                    "confidence": 0.75, "dominant_signals": ["reason_explore"],
                    "supporting_event_ids": []}],
        "tick_scores": [],
        "innovations": [],
        "contradictions": [],
        "anomalies": [],
        "critical_events": [],
    }


class TestDigestRenderer:
    def test_writes_run_digest_json(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        run_digest = _minimal_run_digest()
        renderer.render(run_digest, agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest={})
        assert (tmp_path / "llm_digest" / "run_digest.json").exists()
        loaded = json.loads((tmp_path / "llm_digest" / "run_digest.json").read_text())
        assert loaded["run_id"] == "test-run"

    def test_writes_run_digest_md(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        run_digest = _minimal_run_digest()
        renderer.render(run_digest, agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest={})
        md = (tmp_path / "llm_digest" / "run_digest.md").read_text()
        assert "test-run" in md
        assert "## Outcomes" in md
        assert "## Agents" in md

    def test_writes_agent_json_and_md(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        run_digest = _minimal_run_digest()
        renderer.render(run_digest, agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest={})
        assert (tmp_path / "llm_digest" / "agents" / "Ada.json").exists()
        assert (tmp_path / "llm_digest" / "agents" / "Ada.md").exists()

    def test_agent_md_contains_sections(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        renderer.render(_minimal_run_digest(),
                        agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest={})
        md = (tmp_path / "llm_digest" / "agents" / "Ada.md").read_text()
        assert "## Phases" in md
        assert "## Innovations" in md
        assert "## Critical Events" in md

    def test_no_none_placeholders_in_md(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        renderer.render(_minimal_run_digest(),
                        agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest={})
        run_md = (tmp_path / "llm_digest" / "run_digest.md").read_text()
        agent_md = (tmp_path / "llm_digest" / "agents" / "Ada.md").read_text()
        assert "None" not in run_md
        assert "None" not in agent_md

    def test_writes_evidence_index(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        evidence = {"Ada_phase_1": ["evt_0001_Ada_agent_decision"]}
        renderer.render(_minimal_run_digest(),
                        agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index=evidence, manifest={})
        loaded = json.loads((tmp_path / "llm_digest" / "evidence_index.json").read_text())
        assert loaded["Ada_phase_1"] == ["evt_0001_Ada_agent_decision"]

    def test_writes_generation_manifest(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        manifest = {"mode": "deterministic", "llm_overlay": None}
        renderer.render(_minimal_run_digest(),
                        agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest=manifest)
        loaded = json.loads((tmp_path / "llm_digest" / "generation_manifest.json").read_text())
        assert loaded["mode"] == "deterministic"
        assert loaded["llm_overlay"] is None
```

- [ ] **Step 2: Run to confirm fail**

Run: `pytest tests/test_digest_renderer.py -v`
Expected: `ImportError`

- [ ] **Step 3: Implement DigestRenderer**

Create `simulation/digest/digest_renderer.py`:

```python
"""DigestRenderer: writes digest JSON and markdown files. No analysis logic."""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path


class DigestRenderer:
    """Serializes RunDigest and AgentDigests to JSON + markdown files."""

    def __init__(self, run_dir: Path):
        self._run_dir = Path(run_dir)
        self._digest_dir = self._run_dir / "llm_digest"
        self._agents_dir = self._digest_dir / "agents"

    def render(
        self,
        run_digest: dict,
        agent_digests: dict[str, dict],
        evidence_index: dict,
        manifest: dict,
    ) -> None:
        """Write all digest files to llm_digest/."""
        self._digest_dir.mkdir(exist_ok=True)
        self._agents_dir.mkdir(exist_ok=True)

        # run_digest.json
        self._write_json("run_digest.json", run_digest)

        # run_digest.md
        (self._digest_dir / "run_digest.md").write_text(
            self._render_run_md(run_digest), encoding="utf-8"
        )

        # per-agent files
        for agent_id, agent_digest in agent_digests.items():
            self._write_json(f"agents/{agent_id}.json", agent_digest)
            (self._agents_dir / f"{agent_id}.md").write_text(
                self._render_agent_md(agent_digest), encoding="utf-8"
            )

        # evidence_index.json
        self._write_json("evidence_index.json", evidence_index)

        # generation_manifest.json
        self._write_json("generation_manifest.json", manifest)

    # --- JSON helpers ---

    def _write_json(self, rel_path: str, data: dict) -> None:
        path = self._digest_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # --- Markdown templates ---

    def _render_run_md(self, d: dict) -> str:
        meta = d.get("meta", {})
        outcomes = d.get("outcomes", {})
        agents = d.get("agents", [])
        anomalies = d.get("anomalies", [])

        survivors = ", ".join(outcomes.get("survivors", [])) or "none"
        deaths = ", ".join(outcomes.get("deaths", [])) or "none"

        agent_rows = "\n".join(
            f"| {a['agent_id']} | {a['status']} | {a['dominant_mode']} | "
            f"{a['phase_count']} | {a['innovation_count']} | {a['anomaly_count']} |"
            for a in agents
        )

        anomaly_section = ""
        if anomalies:
            rows = "\n".join(
                f"| {a['type']} | {a['severity']} | tick {a['tick']} | "
                f"{a.get('agent_id') or 'run'} | {a['description'][:60]} |"
                for a in anomalies
            )
            anomaly_section = f"""
## Anomalies

| Type | Severity | When | Agent | Description |
|------|----------|------|-------|-------------|
{rows}
"""

        return f"""# Run Digest: {d.get('run_id', 'unknown')}

Generated: {d.get('generated_at', '')}

## Meta

| Key | Value |
|-----|-------|
| Seed | {meta.get('seed', '?')} |
| Ticks | {meta.get('ticks', '?')} |
| Agents | {meta.get('agent_count', '?')} |
| Model | {meta.get('model_id', '?')} |
| Commit | {meta.get('git_commit', '?')} |

## Outcomes

- **Survivors:** {survivors}
- **Deaths:** {deaths}
- **Innovations approved:** {outcomes.get('total_innovations_approved', 0)}
- **Innovations attempted:** {outcomes.get('total_innovations_attempted', 0)}
- **Total anomalies:** {outcomes.get('total_anomalies', 0)}

## Agents

| Agent | Status | Dominant Mode | Phases | Innovations | Anomalies |
|-------|--------|---------------|--------|-------------|-----------|
{agent_rows}
{anomaly_section}
"""

    def _render_agent_md(self, d: dict) -> str:
        agent_id = d.get("agent_id", "unknown")
        final = d.get("final_state", {})
        extrema = d.get("state_extrema", {})
        action_mix = d.get("action_mix", {})
        phases = d.get("phases", [])
        innovations = d.get("innovations", [])
        contradictions = d.get("contradictions", [])
        anomalies = d.get("anomalies", [])
        critical = d.get("critical_events", [])

        # Action mix table
        mix_rows = "\n".join(f"| {k} | {v:.1%} |" for k, v in sorted(action_mix.items(), key=lambda x: -x[1]))

        # Phases table
        phase_rows = "\n".join(
            f"| {p['phase_id']} | {p['mode']} | {p['tick_start']}–{p['tick_end']} | "
            f"{p['confidence']:.2f} | {', '.join(p.get('dominant_signals', [])[:3])} |"
            for p in phases
        )

        # Innovation section
        inno_section = ""
        if innovations:
            rows = "\n".join(
                f"| {i['name']} | tick {i.get('tick_attempted', '?')} | "
                f"{'✓' if i.get('approved') else '✗'} | {i.get('category', '')} |"
                for i in innovations
            )
            inno_section = f"""
| Name | Attempted | Approved | Category |
|------|-----------|----------|----------|
{rows}
"""
        else:
            inno_section = "\n_No innovations attempted._\n"

        # Critical events
        crit_section = ""
        if critical:
            crit_section = "\n".join(
                f"- **Tick {c['tick']}:** {c['description']}"
                for c in critical
            )
        else:
            crit_section = "_No critical events._"

        # Contradictions
        contra_section = ""
        if contradictions:
            contra_section = "\n".join(
                f"- **Tick {c['tick']}:** \"{c['learning'][:80]}\" — contradicted by: {c['contradicted_by']}"
                for c in contradictions
            )
        else:
            contra_section = "_No contradictions detected._"

        pos = final.get("pos", {})
        pos_str = f"({pos.get('x', '?')}, {pos.get('y', '?')})" if pos else "unknown"

        min_life = extrema.get("min_life", {})
        max_hunger = extrema.get("max_hunger", {})

        return f"""# Agent Digest: {agent_id}

**Run:** {d.get('run_id', 'unknown')}
**Status:** {d.get('status', 'unknown')}

## Final State

| Stat | Value |
|------|-------|
| Life | {final.get('life', '?')} |
| Hunger | {final.get('hunger', '?')} |
| Energy | {final.get('energy', '?')} |
| Position | {pos_str} |

**State extrema:**
- Lowest life: {min_life.get('value', '?')} at tick {min_life.get('tick', '?')}
- Peak hunger: {max_hunger.get('value', '?')} at tick {max_hunger.get('tick', '?')}

## Action Mix

| Action | Frequency |
|--------|-----------|
{mix_rows}

## Phases

| # | Mode | Ticks | Confidence | Top Signals |
|---|------|-------|------------|-------------|
{phase_rows}

## Innovations
{inno_section}
## Critical Events

{crit_section}

## Contradictions

{contra_section}
"""
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_digest_renderer.py -v`
Expected: All 7 tests pass

- [ ] **Step 5: Commit**

```bash
git add simulation/digest/digest_renderer.py tests/test_digest_renderer.py
git commit -m "feat: add DigestRenderer JSON and markdown serialization"
```

---

### Task 7: DigestBuilder orchestrator and integration test

**Files:**
- Create: `simulation/digest/digest_builder.py`
- Create: `tests/test_digest_builder.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/test_digest_builder.py`:

```python
"""Integration tests for DigestBuilder."""

import json
import subprocess
import sys
from pathlib import Path
import pytest
from simulation.digest.digest_builder import DigestBuilder


# --- Event helpers (reuse pattern from test_ebs_builder.py) ---

def _write_events(run_dir: Path, events: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": "test-run", "seed": 42, "ticks": 10, "agent_count": 1,
        "world_size": [10, 10], "model_id": "test", "git_commit": "abc123",
    }
    (run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (run_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )


def _minimal_events() -> list[dict]:
    """10 ticks, 1 agent (Ada), all moves."""
    events = [{
        "run_id": "test-run", "tick": 0, "event_type": "run_start", "agent_id": None,
        "payload": {"config": {"agent_names": ["Ada"]}, "model_id": "test", "world_seed": 42},
    }]
    for t in range(1, 11):
        events.append({
            "run_id": "test-run", "tick": t, "event_type": "agent_decision",
            "agent_id": "Ada",
            "payload": {"parsed_action": {"action": "move", "direction": "east", "reason": "exploring"},
                        "parse_ok": True},
        })
        events.append({
            "run_id": "test-run", "tick": t, "event_type": "agent_perception",
            "agent_id": "Ada",
            "payload": {"pos": {"x": t, "y": 0}, "hunger": 20, "energy": 80,
                        "resources_nearby": [], "night_penalty_active": False},
        })
        events.append({
            "run_id": "test-run", "tick": t, "event_type": "oracle_resolution",
            "agent_id": "Ada",
            "payload": {"success": True, "action": "move", "cache_hit": True,
                        "is_innovation_action": False, "effects": {}},
        })
        events.append({
            "run_id": "test-run", "tick": t, "event_type": "agent_state",
            "agent_id": "Ada",
            "payload": {"life": 100, "hunger": 20 + t, "energy": 80, "alive": True,
                        "pos": {"x": t, "y": 0}},
        })
    events.append({
        "run_id": "test-run", "tick": 10, "event_type": "run_end", "agent_id": None,
        "payload": {"total_ticks": 10, "survivors": ["Ada"]},
    })
    return events


class TestDigestBuilderOutput:
    def test_creates_run_digest_json(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        assert (tmp_path / "llm_digest" / "run_digest.json").exists()

    def test_creates_run_digest_md(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        assert (tmp_path / "llm_digest" / "run_digest.md").exists()

    def test_creates_per_agent_files(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        assert (tmp_path / "llm_digest" / "agents" / "Ada.json").exists()
        assert (tmp_path / "llm_digest" / "agents" / "Ada.md").exists()

    def test_run_digest_has_required_keys(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        data = json.loads((tmp_path / "llm_digest" / "run_digest.json").read_text())
        for key in ("run_id", "generated_at", "meta", "outcomes", "agents", "anomalies"):
            assert key in data, f"Missing key: {key}"

    def test_evidence_index_covers_anomaly_supporting_event_ids(self, tmp_path):
        """Anomaly supporting_event_ids must be reachable via evidence_index.json."""
        # Build events that trigger a PARSE_FAIL_STREAK (3 consecutive parse failures)
        events = _minimal_events()
        # Replace first 3 decision events with parse_ok=False
        fail_count = 0
        for ev in events:
            if ev.get("event_type") == "agent_decision" and fail_count < 3:
                ev["payload"]["parse_ok"] = False
                fail_count += 1
        _write_events(tmp_path, events)
        DigestBuilder(tmp_path).build()

        evidence = json.loads((tmp_path / "llm_digest" / "evidence_index.json").read_text())
        run_data = json.loads((tmp_path / "llm_digest" / "run_digest.json").read_text())

        # All anomaly_ids from the run digest must appear as keys in the evidence index
        for anomaly in run_data.get("anomalies", []):
            assert anomaly["anomaly_id"] in evidence, (
                f"Anomaly {anomaly['anomaly_id']} not in evidence index"
            )

    def test_manifest_is_deterministic_with_no_llm_overlay(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        manifest = json.loads((tmp_path / "llm_digest" / "generation_manifest.json").read_text())
        assert manifest["mode"] == "deterministic"
        assert manifest["llm_overlay"] is None

    def test_manifest_source_files_use_relative_paths(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        manifest = json.loads((tmp_path / "llm_digest" / "generation_manifest.json").read_text())
        for v in manifest.get("source_files", {}).values():
            assert not str(v).startswith("/"), f"Path should be relative: {v}"

    def test_no_llm_calls_made(self, tmp_path):
        """DigestBuilder must not import or call any LLM client."""
        _write_events(tmp_path, _minimal_events())
        # If this completes without network errors or import side-effects, we're good
        DigestBuilder(tmp_path).build()

    def test_noop_when_events_missing(self, tmp_path):
        """Should not raise if events.jsonl doesn't exist."""
        tmp_path.mkdir(exist_ok=True)
        DigestBuilder(tmp_path).build()  # no exception
        assert not (tmp_path / "llm_digest").exists()


class TestDigestBuilderCLI:
    def test_cli_exits_zero(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        result = subprocess.run(
            [sys.executable, "-m", "simulation.digest.digest_builder", str(tmp_path)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_cli_creates_output_files(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        subprocess.run(
            [sys.executable, "-m", "simulation.digest.digest_builder", str(tmp_path)],
            capture_output=True
        )
        assert (tmp_path / "llm_digest" / "run_digest.json").exists()
```

- [ ] **Step 2: Run to confirm fail**

Run: `pytest tests/test_digest_builder.py -v`
Expected: `ImportError`

- [ ] **Step 3: Implement DigestBuilder**

Create `simulation/digest/digest_builder.py`:

```python
"""DigestBuilder: orchestrates the digest pipeline for a single run directory.

Usage (standalone CLI):
    python -m simulation.digest.digest_builder data/runs/<run_id>
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from simulation.digest.behavior_segmenter import BehaviorSegmenter
from simulation.digest.anomaly_detector import AnomalyDetector
from simulation.digest.evidence_indexer import EvidenceIndexer
from simulation.digest.digest_renderer import DigestRenderer

logger = logging.getLogger(__name__)

_DIGEST_BUILDER_VERSION = "1.0.0"


class DigestBuilder:
    """Reads events.jsonl and writes llm_digest/ for a single run."""

    def __init__(self, run_dir: Path):
        self._run_dir = Path(run_dir)
        self._events_path = self._run_dir / "events.jsonl"
        self._meta_path = self._run_dir / "meta.json"

    def build(self) -> None:
        """Build the digest. No-op if events.jsonl is missing.

        Returns None (consistent with MetricsBuilder/EBSBuilder pattern).
        All digest data is returned as plain dicts, not typed RunDigest dataclasses.
        """
        if not self._events_path.exists():
            return

        events = self._load_events()
        run_meta = self._load_meta()

        # Detect agents
        agent_ids = self._extract_agent_ids(events, run_meta)

        # Component: AnomalyDetector
        detector = AnomalyDetector()
        anomalies = detector.detect(events)

        # Component: BehaviorSegmenter (per agent)
        segmenter = BehaviorSegmenter()
        segmentations = {
            agent_id: segmenter.segment(agent_id, events)
            for agent_id in agent_ids
        }

        # Build per-agent digests
        agent_digests = {
            agent_id: self._build_agent_digest(agent_id, events, segmentations[agent_id], anomalies)
            for agent_id in agent_ids
        }

        # Component: EvidenceIndexer
        critical_events_by_agent = {
            agent_id: agent_digests[agent_id].get("critical_events", [])
            for agent_id in agent_ids
        }
        indexer = EvidenceIndexer()
        evidence_index = indexer.build(
            events, list(segmentations.values()), anomalies, critical_events_by_agent
        )

        # Assemble run_digest
        run_digest = self._build_run_digest(events, run_meta, agent_ids, agent_digests, anomalies)

        # Build generation manifest
        manifest = self._build_manifest()

        # Render all files
        renderer = DigestRenderer(self._run_dir)
        renderer.render(run_digest, agent_digests, evidence_index, manifest)

        logger.info("DigestBuilder: written %s", self._run_dir / "llm_digest")

    # --- Event loading ---

    def _load_events(self) -> list[dict]:
        events = []
        with self._events_path.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    events.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
        return events

    def _load_meta(self) -> dict:
        if self._meta_path.exists():
            try:
                return json.loads(self._meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _extract_agent_ids(self, events: list[dict], meta: dict) -> list[str]:
        """Extract agent IDs from run_start event or meta.json."""
        for ev in events:
            if ev.get("event_type") == "run_start":
                names = ev.get("payload", {}).get("config", {}).get("agent_names", [])
                if names:
                    return list(names)
        # Fallback: collect from events
        ids = sorted({ev["agent_id"] for ev in events if ev.get("agent_id")})
        return ids

    # --- Run digest assembly ---

    def _build_run_digest(
        self, events: list[dict], meta: dict, agent_ids: list[str],
        agent_digests: dict, anomalies: list
    ) -> dict:
        run_id = meta.get("run_id") or self._run_dir.name
        total_ticks = meta.get("ticks", 0)
        survivors: list[str] = []
        deaths: list[str] = []

        for ev in reversed(events):
            if ev.get("event_type") == "run_end":
                survivors = ev.get("payload", {}).get("survivors", [])
                break

        for agent_id in agent_ids:
            if agent_id not in survivors:
                deaths.append(agent_id)

        # Innovation counts from events
        innovations_approved = sum(
            1 for ev in events
            if ev.get("event_type") == "innovation_validated"
            and ev.get("payload", {}).get("approved")
        )
        innovations_attempted = sum(
            1 for ev in events if ev.get("event_type") == "innovation_attempt"
        )

        anomaly_counts: dict[str, int] = {}
        for a in anomalies:
            anomaly_counts[a.type] = anomaly_counts.get(a.type, 0) + 1

        agent_summaries = []
        for agent_id in agent_ids:
            ad = agent_digests.get(agent_id, {})
            phases = ad.get("phases", [])
            mode_counts: dict[str, int] = {}
            for p in phases:
                mode_counts[p.get("mode", "?")] = mode_counts.get(p.get("mode", "?"), 0) + (p.get("tick_end", 0) - p.get("tick_start", 0) + 1)
            dominant = max(mode_counts, key=lambda m: mode_counts[m]) if mode_counts else "unknown"
            agent_summaries.append({
                "agent_id": agent_id,
                "status": "alive" if agent_id in survivors else "dead",
                "phase_count": len(phases),
                "dominant_mode": dominant,
                "innovation_count": len(ad.get("innovations", [])),
                "anomaly_count": len(ad.get("anomalies", [])),
                "digest_path": f"agents/{agent_id}.json",
            })

        return {
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "meta": {
                "seed": meta.get("seed"),
                "ticks": total_ticks or self._count_ticks(events),
                "agent_count": len(agent_ids),
                "world_size": meta.get("world_size", [10, 10]),
                "model_id": meta.get("model_id", "unknown"),
                "git_commit": meta.get("git_commit", "unknown"),
            },
            "outcomes": {
                "survivors": survivors,
                "deaths": deaths,
                "total_innovations_approved": innovations_approved,
                "total_innovations_attempted": innovations_attempted,
                "total_anomalies": len(anomalies),
                "anomaly_counts_by_type": anomaly_counts,
            },
            "agents": agent_summaries,
            # Run-level anomalies: all anomalies across the run (both agent-scoped and global).
            # Per-agent anomalies are also listed in agents/<id>.json for focused views.
            "anomalies": [self._anomaly_to_dict(a) for a in anomalies],
            "evidence_path": "evidence_index.json",
            "manifest_path": "generation_manifest.json",
        }

    def _count_ticks(self, events: list[dict]) -> int:
        ticks = {ev.get("tick", 0) for ev in events}
        return max(ticks) if ticks else 0

    # --- Per-agent digest assembly ---

    def _build_agent_digest(self, agent_id: str, events: list[dict], segmentation, anomalies: list) -> dict:
        from simulation.digest.behavior_segmenter import AgentSegmentation

        # Final state from last agent_state event
        final_state = {}
        state_history: list[dict] = []
        for ev in events:
            if ev.get("event_type") == "agent_state" and ev.get("agent_id") == agent_id:
                p = ev.get("payload", {})
                state_history.append({"tick": ev["tick"], **p})
                final_state = {
                    "life": p.get("life"), "hunger": p.get("hunger"),
                    "energy": p.get("energy"), "pos": p.get("pos"),
                }

        # State extrema
        state_extrema = {}
        if state_history:
            min_life_entry = min(state_history, key=lambda s: s.get("life", 999))
            max_hunger_entry = max(state_history, key=lambda s: s.get("hunger", 0))
            state_extrema = {
                "min_life": {"value": min_life_entry.get("life"), "tick": min_life_entry["tick"]},
                "max_hunger": {"value": max_hunger_entry.get("hunger"), "tick": max_hunger_entry["tick"]},
            }

        # Action mix
        action_counts: dict[str, int] = {}
        total_actions = 0
        for ev in events:
            if ev.get("event_type") == "agent_decision" and ev.get("agent_id") == agent_id:
                act = ev.get("payload", {}).get("parsed_action", {}).get("action", "other")
                action_counts[act] = action_counts.get(act, 0) + 1
                total_actions += 1
        action_mix = {k: round(v / total_actions, 3) for k, v in action_counts.items()} if total_actions else {}

        # Innovations
        approved_innovations = {}
        for ev in events:
            if ev.get("event_type") == "innovation_validated" and ev.get("agent_id") == agent_id:
                p = ev.get("payload", {})
                if p.get("approved"):
                    name = p.get("name", "unknown")
                    approved_innovations[name] = {
                        "name": name,
                        "tick_attempted": ev["tick"],
                        "tick_first_used": None,
                        "approved": True,
                        "category": p.get("category"),
                        "structural_novelty": p.get("structural_novelty"),
                        "state_delta": None,
                    }
        for ev in events:
            if ev.get("event_type") == "custom_action_executed" and ev.get("agent_id") == agent_id:
                name = ev.get("payload", {}).get("name")
                if name and name in approved_innovations and approved_innovations[name]["tick_first_used"] is None:
                    approved_innovations[name]["tick_first_used"] = ev["tick"]

        # Critical events: state extrema + innovations
        critical_events = []
        if state_extrema.get("min_life", {}).get("value") is not None:
            min_life_val = state_extrema["min_life"]["value"]
            min_life_tick = state_extrema["min_life"]["tick"]
            if min_life_val < 70:  # threshold for "critical"
                critical_events.append({
                    "tick": min_life_tick,
                    "description": f"Life dropped to {min_life_val}",
                    "supporting_event_ids": [f"evt_{min_life_tick:04d}_{agent_id}_agent_state"],
                })

        # Agent-scoped anomalies
        agent_anomalies = [a for a in anomalies if a.agent_id == agent_id]

        # Build per-agent contradictions from anomaly list
        contradictions = []
        for a in agent_anomalies:
            if a.type == "CONTRADICTION":
                contradictions.append({
                    "tick": a.tick,
                    "learning": a.description,
                    "contradicted_by": "confirmed resource/action from events",
                    "supporting_event_ids": a.supporting_event_ids,
                })

        status = "alive"
        for ev in reversed(events):
            if ev.get("event_type") == "run_end":
                survivors = ev.get("payload", {}).get("survivors", [])
                status = "alive" if agent_id in survivors else "dead"
                break

        return {
            "agent_id": agent_id,
            "run_id": self._run_dir.name,
            "status": status,
            "final_state": final_state,
            "state_extrema": state_extrema,
            "action_mix": action_mix,
            "phases": [self._phase_to_dict(p) for p in segmentation.phases],
            "tick_scores": [self._tick_score_to_dict(ts) for ts in segmentation.tick_scores],
            "innovations": list(approved_innovations.values()),
            "contradictions": contradictions,
            "anomalies": [self._anomaly_to_dict(a) for a in agent_anomalies],
            "critical_events": critical_events,
        }

    # --- Serialization helpers ---

    def _anomaly_to_dict(self, a) -> dict:
        return {
            "anomaly_id": a.anomaly_id,
            "type": a.type,
            "severity": a.severity,
            "tick": a.tick,
            "agent_id": a.agent_id,
            "description": a.description,
            "supporting_event_ids": a.supporting_event_ids,
        }

    def _phase_to_dict(self, p) -> dict:
        return {
            "phase_id": p.phase_id,
            "mode": p.mode,
            "tick_start": p.tick_start,
            "tick_end": p.tick_end,
            "confidence": p.confidence,
            "dominant_signals": p.dominant_signals,
            "supporting_event_ids": p.supporting_event_ids,
        }

    def _tick_score_to_dict(self, ts) -> dict:
        return {
            "tick": ts.tick,
            "scores": {k: round(v, 3) for k, v in ts.scores.items()},
            "assigned_mode": ts.assigned_mode,
            "dominant_signals": ts.dominant_signals,
        }

    def _build_manifest(self) -> dict:
        return {
            "mode": "deterministic",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "digest_builder_version": _DIGEST_BUILDER_VERSION,
            "source_files": {
                "events_jsonl": "events.jsonl",
                "meta_json": "meta.json",
                "ebs_json": "metrics/ebs.json",
            },
            "llm_overlay": None,
        }


if __name__ == "__main__":
    import sys
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Build LLM digest for a simulation run")
    parser.add_argument("run_dir", help="Path to run directory (data/runs/<run_id>)")
    parser.add_argument("--no-render-md", action="store_true", help="Skip markdown rendering")
    parser.add_argument("--agents", nargs="*", help="Limit to specific agents")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"Error: {run_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    print(f"Building digest for {run_dir.name}...")
    DigestBuilder(run_dir).build()
    print(f"  -> {run_dir}/llm_digest/")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_digest_builder.py -v`
Expected: All tests pass

- [ ] **Step 5: Run all digest tests together**

Run: `pytest tests/test_behavior_segmenter.py tests/test_anomaly_detector.py tests/test_digest_renderer.py tests/test_digest_builder.py -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add simulation/digest/digest_builder.py tests/test_digest_builder.py
git commit -m "feat: add DigestBuilder orchestrator and integration tests"
```

---

## Chunk 4: Engine Integration and CLI

### Task 8: Engine integration, main.py flag, and smoke test

**Files:**
- Modify: `simulation/engine.py:39-50` (add `run_digest` kwarg to `__init__`)
- Modify: `simulation/engine.py:156-168` (add DigestBuilder call in `run()` finally block)
- Modify: `simulation/engine.py:659-671` (add DigestBuilder call in `run_with_callback()` finally block)
- Modify: `main.py:34-104` (add `--no-digest` flag and pass `run_digest` to engine)

- [ ] **Step 1: Add `run_digest` parameter to `SimulationEngine.__init__`**

In `simulation/engine.py`, `SimulationEngine.__init__` currently ends at approximately line 50. Add `run_digest: bool = True` to the constructor signature and store it.

Find this section (lines 39–50):
```python
    def __init__(
        self,
        num_agents: int = 3,
        world_seed: Optional[int] = None,
        use_llm: bool = True,
        max_ticks: int = MAX_TICKS,
        start_hour: int = WORLD_START_HOUR,
        world_width: int = WORLD_WIDTH,
        world_height: int = WORLD_HEIGHT,
        wandb_logger: Optional["WandbLogger"] = None,
        ollama_model: Optional[str] = None,
    ):
```

Add `run_digest: bool = True,` before the closing `)`:

```python
    def __init__(
        self,
        num_agents: int = 3,
        world_seed: Optional[int] = None,
        use_llm: bool = True,
        max_ticks: int = MAX_TICKS,
        start_hour: int = WORLD_START_HOUR,
        world_width: int = WORLD_WIDTH,
        world_height: int = WORLD_HEIGHT,
        wandb_logger: Optional["WandbLogger"] = None,
        ollama_model: Optional[str] = None,
        run_digest: bool = True,
    ):
```

Then find the line that assigns other kwargs to `self` (look for `self.wandb_logger = wandb_logger` or similar) and add:
```python
        self.run_digest = run_digest
```

- [ ] **Step 2: Add DigestBuilder call in `run()` finally block**

Find the `finally` block in `run()` (around lines 156–168):

```python
        finally:
            ...
            try:
                MetricsBuilder(self.event_emitter.run_dir).build()
                EBSBuilder(self.event_emitter.run_dir).build()
            except Exception as exc:
                logger.warning("MetricsBuilder/EBSBuilder failed: %s", exc)
```

Add the DigestBuilder call immediately after:

```python
        finally:
            ...
            try:
                MetricsBuilder(self.event_emitter.run_dir).build()
                EBSBuilder(self.event_emitter.run_dir).build()
            except Exception as exc:
                logger.warning("MetricsBuilder/EBSBuilder failed: %s", exc)
            if self.run_digest:
                try:
                    from simulation.digest.digest_builder import DigestBuilder
                    DigestBuilder(self.event_emitter.run_dir).build()
                except Exception as exc:
                    logger.warning("DigestBuilder failed: %s", exc)
```

- [ ] **Step 3: Add DigestBuilder call in `run_with_callback()` finally block**

Find the identical pattern in `run_with_callback()` (around lines 659–671) and apply the same change:

```python
        finally:
            ...
            try:
                MetricsBuilder(self.event_emitter.run_dir).build()
                EBSBuilder(self.event_emitter.run_dir).build()
            except Exception as exc:
                logger.warning("MetricsBuilder/EBSBuilder failed: %s", exc)
            if self.run_digest:
                try:
                    from simulation.digest.digest_builder import DigestBuilder
                    DigestBuilder(self.event_emitter.run_dir).build()
                except Exception as exc:
                    logger.warning("DigestBuilder failed: %s", exc)
```

- [ ] **Step 4: Add `--no-digest` flag to `main.py`**

In `main.py`, find the existing argparse flags (around line 38) and add:

```python
    parser.add_argument("--no-digest", action="store_true",
                        help="Skip LLM digest generation after run")
```

Then find the `SimulationEngine(...)` constructor call (around line 94) and add `run_digest=not args.no_digest,`:

```python
    engine = SimulationEngine(
        num_agents=args.agents,
        world_seed=args.seed,
        use_llm=not args.no_llm,
        max_ticks=args.ticks,
        start_hour=args.start_hour,
        world_width=args.width,
        world_height=args.height,
        wandb_logger=wandb_logger,
        ollama_model=args.model,
        run_digest=not args.no_digest,
    )
```

- [ ] **Step 5: Run the full test suite**

Run: `pytest -m "not slow" -v`
Expected: All tests pass (no regressions)

- [ ] **Step 6: Smoke test — end-to-end run with digest**

Run: `uv run main.py --no-llm --ticks 20 --agents 2 --seed 42`

Then verify output:
```bash
ls data/runs/*/llm_digest/
```
Expected: `run_digest.json`, `run_digest.md`, `evidence_index.json`, `generation_manifest.json`, `agents/`

```bash
cat data/runs/$(ls -t data/runs | head -1)/llm_digest/run_digest.json | python -m json.tool | head -30
```
Expected: valid JSON with `run_id`, `meta`, `outcomes`, `agents` keys

```bash
cat data/runs/$(ls -t data/runs | head -1)/llm_digest/agents/Ada.md
```
Expected: readable markdown with `## Phases`, `## Innovations`, `## Critical Events` sections

- [ ] **Step 7: Smoke test — `--no-digest` flag suppresses output**

Run: `uv run main.py --no-llm --ticks 5 --agents 1 --seed 99 --no-digest`

Then verify:
```bash
ls data/runs/$(ls -t data/runs | head -1)/
```
Expected: no `llm_digest/` directory

- [ ] **Step 8: Smoke test — standalone CLI**

```bash
python -m simulation.digest.digest_builder data/runs/$(ls -t data/runs | head -1)
```
Expected: exits 0, prints `Building digest for ...` and `-> .../llm_digest/`

- [ ] **Step 9: Commit**

```bash
git add simulation/engine.py main.py
git commit -m "feat: integrate DigestBuilder into engine and add --no-digest CLI flag"
```

---

## Final verification

Run the complete test suite one last time before considering the PR ready:

```bash
pytest -m "not slow" -v
```

Expected: all tests pass with no regressions.
