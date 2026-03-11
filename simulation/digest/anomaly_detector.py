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
