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
            ev_agent = ev.get("agent_id")
            if ev_agent is not None and ev_agent != agent_id:
                # Skip events from other agents; world-level events (agent_id=None) are included
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
