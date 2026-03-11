"""
MetricsBuilder: reads events.jsonl and writes metrics/summary.json + metrics/timeseries.jsonl.

Usage (standalone):
    uv run python -m simulation.metrics_builder data/runs/<run_id>
    uv run python -m simulation.metrics_builder   # recomputes all runs
"""

import json
from pathlib import Path


class MetricsBuilder:
    """Reads events.jsonl and writes metrics/ directory for a single run."""

    def __init__(self, run_dir: Path):
        self._run_dir = Path(run_dir)
        self._events_path = self._run_dir / "events.jsonl"
        self._metrics_dir = self._run_dir / "metrics"

    def build(self) -> None:
        """Compute and write summary.json + timeseries.jsonl. No-op if events.jsonl missing."""
        if not self._events_path.exists():
            return

        self._metrics_dir.mkdir(exist_ok=True)
        summary, timeseries = self._compute()

        (self._metrics_dir / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        with (self._metrics_dir / "timeseries.jsonl").open("w", encoding="utf-8") as fh:
            for row in timeseries:
                fh.write(json.dumps(row) + "\n")

    def _compute(self) -> tuple[dict, list[dict]]:
        """Single-pass computation over events.jsonl."""
        # --- Accumulators ---
        run_id = None
        total_ticks = 0
        initial_agents: set[str] = set()
        final_survivors: list[str] = []
        deaths = 0

        action_total = 0
        action_by_type: dict[str, int] = {}
        oracle_success_count = 0
        oracle_total = 0
        parse_fail_count = 0

        innovation_attempts = 0
        innovation_approved = 0
        innovation_rejected = 0
        innovation_names_approved: set[str] = set()
        innovation_names_used: set[str] = set()

        communication_total = 0
        communication_misunderstood = 0
        symbol_adoptions = 0
        shared_vocab_sum = 0

        # Per-tick buckets (keyed by tick int)
        tick_buckets: dict[int, dict] = {}
        prev_alive: dict[str, bool] = {}

        def bucket(t: int) -> dict:
            if t not in tick_buckets:
                tick_buckets[t] = {
                    "tick": t,
                    "sim_time": None,
                    "states": [],
                    "oracle_success": [],
                    "actions": 0,
                    "deaths": 0,
                    "innovations_attempted": 0,
                    "innovations_approved": 0,
                    "communications": 0,
                    "misunderstandings": 0,
                    "symbol_adoptions": 0,
                    "shared_vocabulary_total": 0,
                    "shared_vocabulary_samples": 0,
                    "run_shared_vocabulary_mean": 0.0,
                    "run_lexicon_mean_size": 0.0,
                }
            return tick_buckets[t]

        # --- Single pass ---
        with self._events_path.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                et = ev.get("event_type")
                tick = ev.get("tick", 0)
                b = bucket(tick)
                if ev.get("sim_time"):
                    b["sim_time"] = ev["sim_time"]

                if et == "run_start":
                    run_id = ev.get("run_id")
                    cfg = ev.get("payload", {}).get("config", {})
                    initial_agents = set(cfg.get("agent_names", []))

                elif et == "run_end":
                    p = ev.get("payload", {})
                    total_ticks = p.get("total_ticks", tick)
                    final_survivors = p.get("survivors", [])

                elif et == "agent_decision":
                    p = ev.get("payload", {})
                    action_total += 1
                    b["actions"] += 1
                    action_name = p.get("parsed_action", {}).get("action", "other")
                    action_by_type[action_name] = action_by_type.get(action_name, 0) + 1
                    if not p.get("parse_ok", True):
                        parse_fail_count += 1

                elif et == "oracle_resolution":
                    p = ev.get("payload", {})
                    oracle_total += 1
                    success = p.get("success", False)
                    if success:
                        oracle_success_count += 1
                    b["oracle_success"].append(success)

                    communication = p.get("communication")
                    if communication:
                        communication_total += 1
                        b["communications"] += 1
                        if communication.get("misunderstood"):
                            communication_misunderstood += 1
                            b["misunderstandings"] += 1
                        adopted = int(communication.get("new_symbols_learned", 0))
                        symbol_adoptions += adopted
                        b["symbol_adoptions"] += adopted
                        shared_size = int(communication.get("shared_vocabulary_size", 0))
                        shared_vocab_sum += shared_size
                        b["shared_vocabulary_total"] += shared_size
                        b["shared_vocabulary_samples"] += 1

                elif et == "agent_state":
                    p = ev.get("payload", {})
                    b["states"].append(p)
                    agent_id = ev.get("agent_id")
                    if agent_id:
                        was_alive = prev_alive.get(agent_id, True)
                        is_alive = p.get("alive", True)
                        if was_alive and not is_alive:
                            b["deaths"] += 1
                            deaths += 1
                        prev_alive[agent_id] = is_alive

                elif et == "language_tick_metrics":
                    p = ev.get("payload", {})
                    b["run_shared_vocabulary_mean"] = p.get("shared_vocabulary_mean", 0.0)
                    b["run_lexicon_mean_size"] = p.get("lexicon_mean_size", 0.0)

                elif et == "innovation_attempt":
                    innovation_attempts += 1
                    b["innovations_attempted"] += 1

                elif et == "innovation_validated":
                    p = ev.get("payload", {})
                    if p.get("approved"):
                        innovation_approved += 1
                        b["innovations_approved"] += 1
                        name = p.get("name")
                        if name:
                            innovation_names_approved.add(name)
                    else:
                        innovation_rejected += 1

                elif et == "custom_action_executed":
                    name = ev.get("payload", {}).get("name")
                    if name:
                        innovation_names_used.add(name)

        # --- Build timeseries (skip tick 0) ---
        timeseries = []
        for t in sorted(tick_buckets):
            if t == 0:
                continue
            b = tick_buckets[t]
            alive_states = [s for s in b["states"] if s.get("alive", True)]
            n = len(alive_states)
            mean_life = round(sum(s.get("life", 0) for s in alive_states) / n, 2) if n else 0.0
            mean_hunger = round(sum(s.get("hunger", 0) for s in alive_states) / n, 2) if n else 0.0
            mean_energy = round(sum(s.get("energy", 0) for s in alive_states) / n, 2) if n else 0.0
            suc = b["oracle_success"]
            oracle_rate = round(sum(suc) / len(suc), 4) if suc else 0.0
            shared_samples = b["shared_vocabulary_samples"]
            shared_mean = round(b["shared_vocabulary_total"] / shared_samples, 3) if shared_samples else 0.0
            misunderstanding_rate = round(b["misunderstandings"] / b["communications"], 4) if b["communications"] else 0.0
            timeseries.append({
                "tick": t,
                "sim_time": b["sim_time"],
                "alive": n,
                "mean_life": mean_life,
                "mean_hunger": mean_hunger,
                "mean_energy": mean_energy,
                "deaths": b["deaths"],
                "actions": b["actions"],
                "oracle_success_rate": oracle_rate,
                "innovations_attempted": b["innovations_attempted"],
                "innovations_approved": b["innovations_approved"],
                "communications": b["communications"],
                "misunderstanding_rate": misunderstanding_rate,
                "symbol_adoptions": b["symbol_adoptions"],
                "shared_vocabulary_mean": shared_mean,
                "run_shared_vocabulary_mean": b["run_shared_vocabulary_mean"],
                "run_lexicon_mean_size": b["run_lexicon_mean_size"],
            })

        # --- Build summary ---
        innovations_used = len(innovation_names_used & innovation_names_approved)
        summary = {
            "run_id": run_id,
            "total_ticks": total_ticks,
            "agents": {
                "initial_count": len(initial_agents),
                "final_survivors": final_survivors,
                "deaths": deaths,
                "survival_rate": round(len(final_survivors) / len(initial_agents), 4) if initial_agents else 0.0,
            },
            "actions": {
                "total": action_total,
                "by_type": action_by_type,
                "oracle_success_rate": round(oracle_success_count / oracle_total, 4) if oracle_total else 0.0,
                "parse_fail_rate": round(parse_fail_count / action_total, 4) if action_total else 0.0,
            },
            "innovations": {
                "attempts": innovation_attempts,
                "approved": innovation_approved,
                "rejected": innovation_rejected,
                "used": innovations_used,
                "approval_rate": round(innovation_approved / innovation_attempts, 4) if innovation_attempts else 0.0,
                "realization_rate": round(innovations_used / innovation_approved, 4) if innovation_approved else 0.0,
            },
            "language": {
                "communications": communication_total,
                "misunderstanding_rate": round(communication_misunderstood / communication_total, 4) if communication_total else 0.0,
                "symbol_adoptions": symbol_adoptions,
                "shared_vocabulary_mean": round(shared_vocab_sum / communication_total, 3) if communication_total else 0.0,
            },
        }
        return summary, timeseries


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        dirs = [Path(sys.argv[1])]
    else:
        runs_root = Path("data") / "runs"
        dirs = sorted(runs_root.iterdir()) if runs_root.exists() else []

    for run_dir in dirs:
        if run_dir.is_dir() and (run_dir / "events.jsonl").exists():
            print(f"Building metrics for {run_dir.name}...")
            MetricsBuilder(run_dir).build()
            print(f"  -> {run_dir}/metrics/")
