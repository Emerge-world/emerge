"""
EBSBuilder: reads events.jsonl and writes metrics/ebs.json.

Computes the Emergent Behaviour Score (EBS) and its five components:
  Novelty, Utility, Realization, Stability, Autonomy

Usage (standalone):
    uv run python -m simulation.ebs_builder data/runs/<run_id>
    uv run python -m simulation.ebs_builder   # recomputes all runs
"""

import json
import math
import re
from pathlib import Path

from simulation.config import EBS_LONGEVITY_REFERENCE_AGENT_TICKS, MEMORY_SEMANTIC_MAX

# Direction string → (dx, dy) for proactive_resource_acquisition
_DIRECTION_TO_DELTA: dict[str, tuple[int, int]] = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

# EBS component weights (must sum to 1.0)
_WEIGHTS = {
    "novelty":     0.25,  # was 0.30
    "utility":     0.17,  # was 0.20
    "realization": 0.17,  # was 0.20
    "stability":   0.13,  # was 0.15
    "autonomy":    0.13,  # was 0.15
    "longevity":   0.15,  # new
}

# Stats that indicate survival value (higher is better for life+energy, lower is better for hunger)
_HUNGER_URGENT_THRESHOLD = 60  # above this → resource-scarce state (environment_contingent_innovation)
_HUNGER_PROACTIVE_THRESHOLD = 60  # below this → hunger non-urgent (proactive move)



def _classify_structural_novelty(requires: dict | None, produces: dict | None, description: str) -> str:
    """Return structural novelty tag for an approved innovation."""
    desc_lower = (description or "").lower()
    prod_keys = set((produces or {}).keys())
    req_items = (requires or {}).get("items", {}) if isinstance(requires, dict) else {}

    # coordination_action: involves other agents
    if any(kw in desc_lower for kw in ("give", "teach", "share", "trade")):
        return "coordination_action"
    if any(kw in prod_keys for kw in ("give", "teach", "share", "trade")):
        return "coordination_action"

    # world_modifying: creates/changes terrain
    if any(kw in prod_keys for kw in ("tile", "terrain", "plant", "build")):
        return "world_modifying"

    # recipe_action: consumes inventory items
    if req_items:
        return "recipe_action"

    # inventory_enabler: produces items (non-stat keys)
    stat_keys = {"hunger", "energy", "life", "health"}
    item_keys = prod_keys - stat_keys
    if item_keys:
        return "inventory_enabler"

    return "base_extension"


def _classify_dependency_depth(requires: dict | None, innovation_names: set[str]) -> int:
    """Return dependency depth 0–3."""
    if not requires or not isinstance(requires, dict):
        return 0
    req_items = requires.get("items", {})
    if req_items:
        # depth 3 if any required item is itself an innovation
        if any(item in innovation_names for item in req_items):
            return 3
        return 2
    if requires.get("tile"):
        return 1
    return 0


def _check_contradiction(learning: str, resource_confirmed: set[str], action_succeeded: set[str]) -> bool:
    """Return True if learning clearly contradicts ground-truth facts."""
    text = learning.lower()

    # Pattern: "no X" / "X not found" / "can't find X" — check against confirmed resources
    for resource in resource_confirmed:
        res = resource.lower()
        if f"no {res}" in text or f"{res} not found" in text or f"can't find {res}" in text:
            return True

    # Pattern: "X never works" / "X doesn't work" — check against succeeded actions
    for action in action_succeeded:
        act = action.lower()
        if f"{act} never works" in text or f"{act} doesn't work" in text:
            return True

    return False


class EBSBuilder:
    """Reads events.jsonl and writes metrics/ebs.json for a single run."""

    def __init__(
        self,
        run_dir: Path,
        longevity_reference_agent_ticks: int = EBS_LONGEVITY_REFERENCE_AGENT_TICKS,
    ):
        self._run_dir = Path(run_dir)
        self._events_path = self._run_dir / "events.jsonl"
        self._metrics_dir = self._run_dir / "metrics"
        self._longevity_reference_agent_ticks = longevity_reference_agent_ticks

    def build(self) -> None:
        """Compute and write ebs.json. No-op if events.jsonl missing."""
        if not self._events_path.exists():
            return

        self._metrics_dir.mkdir(exist_ok=True)
        ebs_data = self._compute()
        (self._metrics_dir / "ebs.json").write_text(
            json.dumps(ebs_data, indent=2), encoding="utf-8"
        )

    def _compute(self) -> dict:
        """Single-pass computation over events.jsonl, then score computation."""
        run_id = None

        # --- Accumulators ---
        innovation_registry: dict[str, dict] = {}  # name → {category, requires, produces, description}
        custom_action_log: list[dict] = []  # {tick, agent_id, name, success}
        state_history: dict[str, list[dict]] = {}  # agent_id → [{tick, hunger, energy, life}]
        perception_log: dict[str, list[dict]] = {}  # agent_id → [{tick, hunger, resources_nearby}]
        decision_log: dict[str, list[dict]] = {}  # agent_id → [{tick, action, direction}]
        learnings_log: list[dict] = []  # {tick, agent_id, learnings}
        resource_confirmed: set[str] = set()  # resource names confirmed consumed/picked up
        action_succeeded: set[str] = set()  # action names confirmed successful by oracle
        plans_created = 0
        subgoals_completed = 0
        subgoals_failed = 0
        parse_fails = 0
        action_total = 0
        innovation_attempts = 0
        innovation_approved = 0
        initial_agents = 0
        total_ticks_from_run_end: int | None = None
        max_tick_seen = 0
        last_semantic: dict[str, int] = {}  # agent_id → final memory_semantic count

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
                agent_id = ev.get("agent_id")
                p = ev.get("payload", {})

                if tick > max_tick_seen:
                    max_tick_seen = tick

                if et == "run_start":
                    run_id = ev.get("run_id")
                    initial_agents = len(p.get("config", {}).get("agent_names", []))

                elif et == "agent_decision":
                    action_total += 1
                    if not p.get("parse_ok", True):
                        parse_fails += 1
                    if agent_id:
                        decision_log.setdefault(agent_id, []).append({
                            "tick": tick,
                            "action": p.get("parsed_action", {}).get("action", ""),
                            "direction": p.get("parsed_action", {}).get("direction", ""),
                        })

                elif et == "agent_state":
                    if agent_id:
                        state_history.setdefault(agent_id, []).append({
                            "tick": tick,
                            "hunger": p.get("hunger", 0),
                            "energy": p.get("energy", 0),
                            "life": p.get("life", 0),
                            "alive": p.get("alive", False),
                        })
                        last_semantic[agent_id] = p.get("memory_semantic", 0)

                elif et == "agent_perception":
                    if agent_id:
                        perception_log.setdefault(agent_id, []).append({
                            "tick": tick,
                            "hunger": p.get("hunger", 0),
                            "resources_nearby": p.get("resources_nearby", []),
                        })

                elif et == "oracle_resolution":
                    if p.get("success"):
                        action_name = p.get("action", "")
                        if action_name in ("eat", "pickup"):
                            # extract resource from effects or message (best-effort)
                            effects = p.get("effects", {})
                            if effects.get("hunger", 0) < 0:
                                resource_confirmed.add("food")
                            resource = p.get("resource") or p.get("item")
                            if resource:
                                resource_confirmed.add(str(resource).lower())
                        if action_name:
                            action_succeeded.add(action_name)

                elif et == "innovation_attempt":
                    innovation_attempts += 1
                    # Capture hunger at this tick for environment_contingent_innovation
                    if agent_id and agent_id in perception_log:
                        percs = perception_log[agent_id]
                        match = next((x for x in reversed(percs) if x["tick"] <= tick), None)
                        if match:
                            # tag this attempt with hunger level
                            innovation_registry.setdefault(f"_attempt_{tick}_{agent_id}", {
                                "tick": tick, "agent_id": agent_id, "hunger": match["hunger"]
                            })

                elif et == "innovation_validated":
                    if p.get("approved"):
                        innovation_approved += 1
                        name = p.get("name", "")
                        if name:
                            innovation_registry[name] = {
                                "category": p.get("category"),
                                "requires": p.get("requires"),
                                "produces": p.get("produces"),
                                "description": p.get("description", ""),
                                "used": False,
                                "first_use_tick": None,
                                "state_delta": None,
                            }

                elif et == "custom_action_executed":
                    name = p.get("name", "")
                    if name and name in innovation_registry:
                        innovation_registry[name]["used"] = True
                        if innovation_registry[name]["first_use_tick"] is None:
                            innovation_registry[name]["first_use_tick"] = tick
                    custom_action_log.append({
                        "tick": tick, "agent_id": agent_id,
                        "name": name, "success": p.get("success", False),
                    })

                elif et == "memory_compression_result":
                    learnings_log.append({
                        "tick": tick, "agent_id": agent_id,
                        "learnings": p.get("learnings", []),
                        "episode_count": p.get("episode_count", 0),
                    })

                elif et == "plan_created":
                    plans_created += 1

                elif et == "subgoal_completed":
                    subgoals_completed += 1

                elif et == "subgoal_failed":
                    subgoals_failed += 1

                elif et == "run_end":
                    total_ticks_from_run_end = p.get("total_ticks")

        # --- Approved innovations only (exclude internal _attempt_ keys) ---
        approved = {k: v for k, v in innovation_registry.items() if not k.startswith("_attempt_")}
        innovation_names = set(approved.keys())

        # --- Classify structural novelty and dependency depth ---
        for name, info in approved.items():
            info["structural_novelty"] = _classify_structural_novelty(
                info.get("requires"), info.get("produces"), info.get("description", "")
            )
            info["dependency_depth"] = _classify_dependency_depth(
                info.get("requires"), innovation_names
            )

        # --- Compute state deltas for Utility ---
        for name, info in approved.items():
            first_tick = info.get("first_use_tick")
            if first_tick is None:
                continue
            # Aggregate agent_state across all agents in window
            def _mean_welfare(states_slice: list[dict]) -> float:
                if not states_slice:
                    return 0.0
                vals = [s["life"] + s["energy"] - s["hunger"] for s in states_slice]
                return sum(vals) / len(vals)

            before, after = [], []
            for agent_states in state_history.values():
                before += [s for s in agent_states if first_tick - 5 <= s["tick"] < first_tick]
                after += [s for s in agent_states if first_tick <= s["tick"] < first_tick + 5]

            delta_welfare = _mean_welfare(after) - _mean_welfare(before)
            info["state_delta"] = {
                "welfare": round(delta_welfare, 2),
                "positive": delta_welfare > 0,
            }

        # --- Contradiction detection ---
        total_learnings = 0
        contradiction_flags = 0
        for entry in learnings_log:
            for learning in entry.get("learnings", []):
                total_learnings += 1
                if _check_contradiction(learning, resource_confirmed, action_succeeded):
                    contradiction_flags += 1

        # --- Compute environment_contingent_innovation from tagged attempts ---
        attempt_entries = [v for k, v in innovation_registry.items() if k.startswith("_attempt_")]
        contingent_attempts = sum(1 for e in attempt_entries if e.get("hunger", 0) > _HUNGER_URGENT_THRESHOLD)

        # --- Compute proactive_resource_acquisition ---
        total_moves = 0
        proactive_moves = 0
        for agent_id, decisions in decision_log.items():
            percs = {p["tick"]: p for p in perception_log.get(agent_id, [])}
            for dec in decisions:
                if dec["action"] != "move":
                    continue
                total_moves += 1
                t = dec["tick"]
                perc = percs.get(t)
                if perc is None:
                    continue
                if perc["hunger"] >= _HUNGER_PROACTIVE_THRESHOLD:
                    continue  # hungry → reactive, not proactive
                direction = (dec.get("direction") or "").lower()
                dx, dy = _DIRECTION_TO_DELTA.get(direction, (None, None))
                if dx is None:
                    continue
                resources = perc.get("resources_nearby", [])
                if any(r.get("dx") == dx and r.get("dy") == dy for r in resources):
                    proactive_moves += 1

        # ---------------------------------------------------------------
        # EBS component scoring
        # ---------------------------------------------------------------
        n_approved = len(approved)
        n_attempts = innovation_attempts
        n_used = sum(1 for info in approved.values() if info.get("used"))
        n_custom = len(custom_action_log)
        n_custom_success = sum(1 for c in custom_action_log if c["success"])

        # Novelty
        # Use per-agent approval count (innovation_approved) for the rate so that
        # multiple agents independently discovering the same innovation are each
        # credited — convergent discovery is realistic emergent behaviour, not waste.
        approval_rate = innovation_approved / n_attempts if n_attempts else 0.0
        categories = {info["category"] for info in approved.values() if info.get("category")}
        category_diversity = len(categories) / 4
        non_base = sum(1 for info in approved.values() if info.get("structural_novelty") != "base_extension")
        structural_originality = non_base / n_approved if n_approved else 0.0
        novelty_score = 100 * (0.40 * approval_rate + 0.30 * category_diversity + 0.30 * structural_originality)

        # Utility
        innovations_with_positive_delta = sum(
            1 for info in approved.values()
            if info.get("state_delta") and info["state_delta"]["positive"]
        )
        direct_state_improvement = innovations_with_positive_delta / n_used if n_used else 0.0
        innovations_with_produces_items = sum(
            1 for info in approved.values()
            if isinstance(info.get("produces"), dict) and
            set(info["produces"].keys()) - {"hunger", "energy", "life", "health"}
        )
        future_option_value = innovations_with_produces_items / n_approved if n_approved else 0.0
        execution_success_rate = n_custom_success / n_custom if n_custom else 0.0
        utility_score = 100 * (0.50 * direct_state_improvement + 0.30 * future_option_value + 0.20 * execution_success_rate)

        # Realization
        use_rate = n_used / n_approved if n_approved else 0.0
        realization_score = 100 * (0.60 * use_rate + 0.40 * execution_success_rate)

        # Stability
        false_knowledge_rate = contradiction_flags / total_learnings if total_learnings else 0.0
        contradiction_rate = false_knowledge_rate  # unified for v1
        invalid_action_rate = parse_fails / action_total if action_total else 0.0
        stability_score = max(0.0, min(100.0,
            100 - 40 * false_knowledge_rate - 30 * invalid_action_rate
        ))

        # Autonomy — rebuilt sub-scores
        # behavioral_initiative: consolidation of two existing behavioral signals
        proactive_rate = proactive_moves / total_moves if total_moves else 0.0
        env_contingent_rate = contingent_attempts / n_attempts if n_attempts else 0.0
        behavioral_initiative = (proactive_rate + env_contingent_rate) / 2

        # knowledge_accumulation: semantic memory growth + compression density
        semantic_growth = (
            sum(v / MEMORY_SEMANTIC_MAX for v in last_semantic.values()) / len(last_semantic)
            if last_semantic else 0.0
        )
        compression_events = [
            e for e in learnings_log if e.get("episode_count", 0) > 0
        ]
        compression_yield = (
            sum(min(1.0, len(e["learnings"]) / e["episode_count"]) for e in compression_events)
            / len(compression_events)
            if compression_events else 0.0
        )
        knowledge_accumulation = (semantic_growth + compression_yield) / 2

        # planning_effectiveness: completion quality + activity quantity
        planning_signal = subgoals_completed + subgoals_failed
        plan_completion_rate = (
            subgoals_completed / planning_signal if planning_signal else 0.0
        )
        planning_activity = min(1.0, planning_signal / action_total) if action_total else 0.0
        planning_effectiveness = (plan_completion_rate + planning_activity) / 2

        autonomy_score = 100 * (
            0.25 * behavioral_initiative
            + 0.375 * knowledge_accumulation
            + 0.375 * planning_effectiveness
        )

        # Longevity
        total_ticks = total_ticks_from_run_end if total_ticks_from_run_end is not None else max_tick_seen
        total_agent_ticks = sum(
            sum(1 for s in states if s.get("alive"))
            for states in state_history.values()
        )
        if initial_agents > 0 and total_ticks > 0:
            population_vitality = total_agent_ticks / (initial_agents * total_ticks)
        else:
            population_vitality = 0.0
        absolute_longevity = 1 - math.exp(-total_agent_ticks / self._longevity_reference_agent_ticks)
        longevity_score = 100 * (0.5 * population_vitality + 0.5 * absolute_longevity)

        # Final EBS
        ebs = (
            _WEIGHTS["novelty"] * novelty_score
            + _WEIGHTS["utility"] * utility_score
            + _WEIGHTS["realization"] * realization_score
            + _WEIGHTS["stability"] * stability_score
            + _WEIGHTS["autonomy"] * autonomy_score
            + _WEIGHTS["longevity"] * longevity_score
        )

        # --- Build output ---
        innovations_list = [
            {
                "name": name,
                "category": info.get("category"),
                "structural_novelty": info.get("structural_novelty"),
                "dependency_depth": info.get("dependency_depth"),
                "used": info.get("used", False),
                "state_delta": info.get("state_delta"),
            }
            for name, info in approved.items()
        ]

        return {
            "run_id": run_id,
            "ebs": round(ebs, 2),
            "components": {
                "novelty": {
                    "score": round(novelty_score, 2),
                    "weight": _WEIGHTS["novelty"],
                    "sub_scores": {
                        "approval_rate": round(approval_rate, 4),
                        "category_diversity": round(category_diversity, 4),
                        "structural_originality": round(structural_originality, 4),
                    },
                },
                "utility": {
                    "score": round(utility_score, 2),
                    "weight": _WEIGHTS["utility"],
                    "sub_scores": {
                        "direct_state_improvement": round(direct_state_improvement, 4),
                        "future_option_value": round(future_option_value, 4),
                        "execution_success_rate": round(execution_success_rate, 4),
                    },
                },
                "realization": {
                    "score": round(realization_score, 2),
                    "weight": _WEIGHTS["realization"],
                    "sub_scores": {
                        "use_rate": round(use_rate, 4),
                        "success_rate": round(execution_success_rate, 4),
                    },
                },
                "stability": {
                    "score": round(stability_score, 2),
                    "weight": _WEIGHTS["stability"],
                    "sub_scores": {
                        "invalid_action_rate": round(invalid_action_rate, 4),
                        "false_knowledge_rate": round(false_knowledge_rate, 4),
                        "contradiction_rate": round(contradiction_rate, 4),
                    },
                },
                "autonomy": {
                    "score": round(autonomy_score, 2),
                    "weight": _WEIGHTS["autonomy"],
                    "sub_scores": {
                        "behavioral_initiative": round(behavioral_initiative, 4),
                        "knowledge_accumulation": round(knowledge_accumulation, 4),
                        "planning_effectiveness": round(planning_effectiveness, 4),
                    },
                    "detail": {
                        "proactive_rate": round(proactive_rate, 4),
                        "env_contingent_rate": round(env_contingent_rate, 4),
                        "semantic_growth": round(semantic_growth, 4),
                        "compression_yield": round(compression_yield, 4),
                        "plan_completion_rate": round(plan_completion_rate, 4),
                        "planning_activity": round(planning_activity, 4),
                    },
                },
                "longevity": {
                    "score": round(longevity_score, 2),
                    "weight": _WEIGHTS["longevity"],
                    "sub_scores": {
                        "population_vitality": round(population_vitality, 4),
                        "absolute_longevity": round(absolute_longevity, 4),
                    },
                },
            },
            "planning": {
                "plans_created": plans_created,
                "subgoals_completed": subgoals_completed,
                "subgoals_failed": subgoals_failed,
            },
            "innovations": innovations_list,
        }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        dirs = [Path(sys.argv[1])]
    else:
        runs_root = Path("data") / "runs"
        dirs = sorted(runs_root.iterdir()) if runs_root.exists() else []

    for run_dir in dirs:
        if run_dir.is_dir() and (run_dir / "events.jsonl").exists():
            print(f"Building EBS for {run_dir.name}...")
            EBSBuilder(run_dir).build()
            print(f"  -> {run_dir}/metrics/ebs.json")
