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
