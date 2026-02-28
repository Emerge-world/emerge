"""
Behavioral audit recorder for prompt A/B testing.

Hooks into the tick loop and writes machine-parseable data:
  audit/events.jsonl  — one line per agent-tick
  audit/meta.json     — run config + prompt hashes + prompt text
  audit/summary.json  — computed behavioral metrics
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional

from simulation.config import (
    AUDIT_HUNGER_THRESHOLD,
    AUDIT_EXHAUSTION_THRESHOLD,
    AUDIT_HUNGER_CRITICAL,
    AGENT_VISION_RADIUS,
)


class AuditRecorder:
    """Records structured behavioral data for prompt comparison."""

    def __init__(self, run_dir: str, config: dict):
        self.audit_dir = os.path.join(run_dir, "audit")
        os.makedirs(self.audit_dir, exist_ok=True)

        self.config = config
        self.events: list[dict] = []

        # Per-agent tracking
        self._agent_positions: dict[str, list[tuple[int, int]]] = {}
        self._agent_spawn: dict[str, tuple[int, int]] = {}
        self._agent_trajectories: dict[str, dict[str, list[int]]] = {}

        # Write meta.json immediately
        self._write_meta()

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    def _write_meta(self):
        """Write run config and prompt hashes to meta.json."""
        prompts_dir = Path(__file__).parent.parent / "prompts"
        prompt_info = {}

        if prompts_dir.exists():
            for txt_file in sorted(prompts_dir.rglob("*.txt")):
                key = str(txt_file.relative_to(prompts_dir))
                content = txt_file.read_text(encoding="utf-8")
                prompt_info[key] = {
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "text": content,
                }

        meta = {
            "config": self.config,
            "prompts": prompt_info,
        }

        with open(os.path.join(self.audit_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------

    def record_event(
        self,
        tick: int,
        agent_name: str,
        stats_before: dict[str, int],
        position_before: tuple[int, int],
        action: str,
        action_source: str,
        oracle_success: bool,
        effects: dict,
        stats_after: dict[str, int],
        position_after: tuple[int, int],
        nearby_tiles: list[dict],
    ):
        """Record a single agent-tick event."""
        # Track positions
        if agent_name not in self._agent_spawn:
            self._agent_spawn[agent_name] = position_before
        self._agent_positions.setdefault(agent_name, []).append(position_after)

        # Track stat trajectories
        traj = self._agent_trajectories.setdefault(
            agent_name, {"life": [], "hunger": [], "energy": []}
        )
        traj["life"].append(stats_after["life"])
        traj["hunger"].append(stats_after["hunger"])
        traj["energy"].append(stats_after["energy"])

        # Compute context flags
        food_tiles = [
            t for t in nearby_tiles
            if "resource" in t and t["resource"].get("type") == "fruit"
        ]
        food_adjacent = any(t["distance"] <= 1 for t in food_tiles)
        food_visible = len(food_tiles) > 0

        # Did agent move toward food?
        moved_toward_food = False
        if action == "move" and oracle_success and food_tiles:
            closest_before = min(
                food_tiles,
                key=lambda t: abs(t["x"] - position_before[0]) + abs(t["y"] - position_before[1]),
            )
            dist_before = abs(closest_before["x"] - position_before[0]) + abs(closest_before["y"] - position_before[1])
            dist_after = abs(closest_before["x"] - position_after[0]) + abs(closest_before["y"] - position_after[1])
            moved_toward_food = dist_after < dist_before

        context_flags = {
            "was_hungry": stats_before["hunger"] > AUDIT_HUNGER_THRESHOLD,
            "was_exhausted": stats_before["energy"] < AUDIT_EXHAUSTION_THRESHOLD,
            "hunger_critical": stats_before["hunger"] > AUDIT_HUNGER_CRITICAL,
            "food_adjacent": food_adjacent,
            "food_visible": food_visible,
            "moved_toward_food": moved_toward_food,
        }

        event = {
            "tick": tick,
            "agent": agent_name,
            "stats_before": stats_before,
            "position_before": list(position_before),
            "action": action,
            "action_source": action_source,
            "oracle_success": oracle_success,
            "effects": effects,
            "stats_after": stats_after,
            "position_after": list(position_after),
            "context_flags": context_flags,
        }

        self.events.append(event)

        # Append to JSONL immediately
        with open(os.path.join(self.audit_dir, "events.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Finalize: compute and write summary
    # ------------------------------------------------------------------

    def finalize(self, max_ticks: int):
        """Compute behavioral metrics and write summary.json."""
        if not self.events:
            summary = {"agents": {}, "aggregate": {}}
            self._write_summary(summary)
            return

        agent_names = sorted(set(e["agent"] for e in self.events))
        per_agent = {}

        for name in agent_names:
            agent_events = [e for e in self.events if e["agent"] == name]
            per_agent[name] = self._compute_agent_metrics(name, agent_events, max_ticks)

        aggregate = self._compute_aggregate(per_agent)

        summary = {
            "agents": per_agent,
            "aggregate": aggregate,
        }
        self._write_summary(summary)

    def _compute_agent_metrics(self, name: str, events: list[dict], max_ticks: int) -> dict:
        """Compute metrics for a single agent."""
        total = len(events)
        if total == 0:
            return {}

        # Survival
        survival_ticks = total
        survival_rate = survival_ticks / max_ticks if max_ticks > 0 else 0.0

        # Action distribution
        action_counts: dict[str, int] = {}
        for e in events:
            a = e["action"]
            action_counts[a] = action_counts.get(a, 0) + 1

        action_pcts = {a: round(c / total, 4) for a, c in action_counts.items()}

        # Oracle success rate
        successes = sum(1 for e in events if e["oracle_success"])
        oracle_success_rate = successes / total if total > 0 else 0.0

        # Per-action success rates
        action_success: dict[str, dict] = {}
        for a in action_counts:
            a_events = [e for e in events if e["action"] == a]
            a_successes = sum(1 for e in a_events if e["oracle_success"])
            action_success[a] = {
                "count": len(a_events),
                "successes": a_successes,
                "rate": round(a_successes / len(a_events), 4) if a_events else 0.0,
            }

        # Reactive intelligence: ate when hungry
        hungry_food_visible = [
            e for e in events
            if e["context_flags"]["was_hungry"] and e["context_flags"]["food_visible"]
        ]
        ate_when_hungry = (
            sum(1 for e in hungry_food_visible if e["action"] == "eat") / len(hungry_food_visible)
            if hungry_food_visible else None
        )

        # Reactive intelligence: rested when exhausted
        exhausted = [e for e in events if e["context_flags"]["was_exhausted"]]
        rested_when_exhausted = (
            sum(1 for e in exhausted if e["action"] == "rest") / len(exhausted)
            if exhausted else None
        )

        # Reactive intelligence: ate when food adjacent
        food_adj = [e for e in events if e["context_flags"]["food_adjacent"]]
        ate_when_food_adjacent = (
            sum(1 for e in food_adj if e["action"] == "eat") / len(food_adj)
            if food_adj else None
        )

        # Exploration
        positions = self._agent_positions.get(name, [])
        unique_tiles = len(set(positions))
        spawn = self._agent_spawn.get(name, (0, 0))
        max_distance = 0
        for px, py in positions:
            d = abs(px - spawn[0]) + abs(py - spawn[1])
            if d > max_distance:
                max_distance = d

        # Innovation
        innovate_events = [e for e in events if e["action"] == "innovate"]
        innovate_successes = sum(1 for e in innovate_events if e["oracle_success"])
        innovation = {
            "count": len(innovate_events),
            "successes": innovate_successes,
            "rate": round(innovate_successes / len(innovate_events), 4) if innovate_events else None,
        }

        # Trajectories
        trajectories = self._agent_trajectories.get(name, {"life": [], "hunger": [], "energy": []})

        return {
            "survival_ticks": survival_ticks,
            "survival_rate": round(survival_rate, 4),
            "action_distribution": action_pcts,
            "oracle_success_rate": round(oracle_success_rate, 4),
            "action_success": action_success,
            "ate_when_hungry": round(ate_when_hungry, 4) if ate_when_hungry is not None else None,
            "rested_when_exhausted": round(rested_when_exhausted, 4) if rested_when_exhausted is not None else None,
            "ate_when_food_adjacent": round(ate_when_food_adjacent, 4) if ate_when_food_adjacent is not None else None,
            "unique_tiles_visited": unique_tiles,
            "max_distance_from_spawn": max_distance,
            "innovation": innovation,
            "trajectories": trajectories,
        }

    def _compute_aggregate(self, per_agent: dict[str, dict]) -> dict:
        """Compute aggregate metrics across all agents."""
        agents = [v for v in per_agent.values() if v]
        if not agents:
            return {}

        n = len(agents)

        survival_rate = sum(a["survival_rate"] for a in agents) / n

        # Mean oracle success
        oracle_success_rate = sum(a["oracle_success_rate"] for a in agents) / n

        # Mean action distribution
        all_actions: set[str] = set()
        for a in agents:
            all_actions.update(a["action_distribution"].keys())
        action_distribution = {}
        for act in sorted(all_actions):
            vals = [a["action_distribution"].get(act, 0.0) for a in agents]
            action_distribution[act] = round(sum(vals) / n, 4)

        # Mean reactive metrics (only from agents where the metric exists)
        def _mean_optional(key: str) -> Optional[float]:
            vals = [a[key] for a in agents if a[key] is not None]
            return round(sum(vals) / len(vals), 4) if vals else None

        ate_when_hungry = _mean_optional("ate_when_hungry")
        rested_when_exhausted = _mean_optional("rested_when_exhausted")
        ate_when_food_adjacent = _mean_optional("ate_when_food_adjacent")

        # Mean exploration
        unique_tiles = sum(a["unique_tiles_visited"] for a in agents) / n
        max_distance = max(a["max_distance_from_spawn"] for a in agents)

        # Mean trajectories
        max_len = max(len(a["trajectories"]["life"]) for a in agents) if agents else 0
        mean_trajectories: dict[str, list[float]] = {"life": [], "hunger": [], "energy": []}
        for i in range(max_len):
            for stat in ("life", "hunger", "energy"):
                vals = [
                    a["trajectories"][stat][i]
                    for a in agents
                    if i < len(a["trajectories"][stat])
                ]
                mean_trajectories[stat].append(round(sum(vals) / len(vals), 1) if vals else 0.0)

        return {
            "num_agents": n,
            "survival_rate": round(survival_rate, 4),
            "oracle_success_rate": round(oracle_success_rate, 4),
            "action_distribution": action_distribution,
            "ate_when_hungry": ate_when_hungry,
            "rested_when_exhausted": rested_when_exhausted,
            "ate_when_food_adjacent": ate_when_food_adjacent,
            "unique_tiles_visited": round(unique_tiles, 1),
            "max_distance_from_spawn": max_distance,
            "mean_trajectories": mean_trajectories,
        }

    def _write_summary(self, summary: dict):
        with open(os.path.join(self.audit_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
