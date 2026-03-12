"""Build scarcity-adaptation metrics from events.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from simulation.config import AGENT_MAX_HUNGER

_FOOD_TYPES = frozenset({"fruit", "mushroom"})


class ScarcityMetricsBuilder:
    """Reads events.jsonl and writes metrics/scarcity.json for a single run."""

    def __init__(self, run_dir: Path):
        self._run_dir = Path(run_dir)
        self._events_path = self._run_dir / "events.jsonl"
        self._metrics_dir = self._run_dir / "metrics"

    def build(self) -> None:
        """Compute and write scarcity.json. No-op if events.jsonl missing."""
        if not self._events_path.exists():
            return

        self._metrics_dir.mkdir(exist_ok=True)
        scarcity = self._compute()
        (self._metrics_dir / "scarcity.json").write_text(
            json.dumps(scarcity, indent=2),
            encoding="utf-8",
        )

    def _compute(self) -> dict:
        run_id = None
        total_ticks = 0
        initial_agents = 0
        tick_states: dict[int, list[dict]] = {}
        prev_alive: dict[str, bool] = {}
        starvation_deaths = 0
        food_consumed: dict[str, int] = {}
        food_regenerated: dict[str, int] = {}
        first_food_tick = None

        with self._events_path.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                run_id = run_id or event.get("run_id")
                event_type = event.get("event_type")
                tick = int(event.get("tick", 0))
                payload = event.get("payload", {})
                agent_id = event.get("agent_id")

                if event_type == "run_start":
                    config = payload.get("config", {})
                    initial_agents = len(config.get("agent_names", []))

                elif event_type == "run_end":
                    total_ticks = int(payload.get("total_ticks", tick))

                elif event_type == "agent_state":
                    tick_states.setdefault(tick, []).append(payload)
                    if agent_id:
                        was_alive = prev_alive.get(agent_id, True)
                        is_alive = payload.get("alive", True)
                        if was_alive and not is_alive and payload.get("hunger", 0) >= AGENT_MAX_HUNGER:
                            starvation_deaths += 1
                        prev_alive[agent_id] = is_alive

                elif event_type == "resource_consumed":
                    resource_type = payload.get("resource_type")
                    quantity = int(payload.get("quantity", 0))
                    if resource_type in _FOOD_TYPES and quantity > 0:
                        food_consumed[resource_type] = food_consumed.get(resource_type, 0) + quantity
                        if first_food_tick is None:
                            first_food_tick = tick

                elif event_type == "resource_regenerated":
                    resource_type = payload.get("resource_type")
                    quantity = int(payload.get("quantity", 0))
                    if resource_type in _FOOD_TYPES and quantity > 0:
                        food_regenerated[resource_type] = food_regenerated.get(resource_type, 0) + quantity

        total_ticks = total_ticks or max(tick_states.keys(), default=0)

        alive_area = 0
        hunger_fraction_total = 0.0
        for tick in range(1, total_ticks + 1):
            states = tick_states.get(tick, [])
            alive_states = [state for state in states if state.get("alive", True)]
            alive_count = len(alive_states)
            alive_area += alive_count
            if alive_states:
                mean_hunger = sum(state.get("hunger", 0) for state in alive_states) / alive_count
                hunger_fraction_total += mean_hunger / AGENT_MAX_HUNGER

        survival_auc = 0.0
        if initial_agents and total_ticks:
            survival_auc = alive_area / (initial_agents * total_ticks)

        mean_hunger_fraction = (hunger_fraction_total / total_ticks) if total_ticks else 0.0
        starvation_death_ratio = (starvation_deaths / initial_agents) if initial_agents else 0.0
        starvation_pressure = 0.7 * mean_hunger_fraction + 0.3 * starvation_death_ratio

        total_food_consumed = sum(food_consumed.values())
        food_conversion_efficiency = alive_area / max(total_food_consumed, 1)

        return {
            "run_id": run_id,
            "total_ticks": total_ticks,
            "initial_agents": initial_agents,
            "alive_area": alive_area,
            "survival_auc": round(survival_auc, 4),
            "starvation_pressure": round(starvation_pressure, 4),
            "food_conversion_efficiency": round(food_conversion_efficiency, 4),
            "starvation_deaths": starvation_deaths,
            "mean_alive_hunger": round(mean_hunger_fraction * AGENT_MAX_HUNGER, 4),
            "food_consumed": food_consumed,
            "food_regenerated": food_regenerated,
            "first_food_tick": first_food_tick,
        }
