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
