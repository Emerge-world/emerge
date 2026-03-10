"""
Canonical event emitter: writes an always-on JSONL event stream per run.

Output: data/runs/<run_id>/
  meta.json     — run config, model, seed, timestamp (written at init)
  events.jsonl  — one JSON object per line, the authoritative data source
"""

import datetime
import json
from pathlib import Path
from typing import Optional

from simulation.config import BASE_ACTIONS
from simulation.day_cycle import DayCycle

_BASE_ACTIONS_SET: frozenset[str] = frozenset(BASE_ACTIONS)


class EventEmitter:
    """Writes a canonical JSONL event stream and meta.json for each run.

    Creates data/runs/<run_id>/ on init and keeps events.jsonl open
    (line-buffered) until close() is called.
    """

    def __init__(
        self,
        run_id: str,
        seed: Optional[int],
        world_width: int,
        world_height: int,
        max_ticks: int,
        agent_count: int,
        agent_names: list[str],
        model_id: str,
        day_cycle: DayCycle,
    ):
        self.run_id = run_id
        self.seed = seed
        self._day_cycle = day_cycle

        run_dir = Path("data") / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Write meta.json immediately so it's available even if the run crashes
        meta = {
            "run_id": run_id,
            "seed": seed,
            "width": world_width,
            "height": world_height,
            "max_ticks": max_ticks,
            "agent_count": agent_count,
            "agent_names": agent_names,
            "model_id": model_id,
            "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # Open events.jsonl with line-buffering so each write flushes automatically
        self._fh = (run_dir / "events.jsonl").open("w", encoding="utf-8", buffering=1)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _sim_time(self, tick: int) -> Optional[dict]:
        """Return {"day": N, "hour": H} for tick > 0, None for tick == 0."""
        if tick == 0:
            return None
        return {"day": self._day_cycle.get_day(tick), "hour": self._day_cycle.get_hour(tick)}

    def _emit(self, event_type: str, tick: int, payload: dict, agent_id: Optional[str] = None):
        event = {
            "run_id": self.run_id,
            "seed": self.seed,
            "tick": tick,
            "sim_time": self._sim_time(tick),
            "event_type": event_type,
            "agent_id": agent_id,
            "payload": payload,
        }
        self._fh.write(json.dumps(event) + "\n")

    @staticmethod
    def _action_origin(action_name: str) -> str:
        return "base" if action_name in _BASE_ACTIONS_SET else "innovation"

    # ------------------------------------------------------------------ #
    # Public emit methods (called from engine.py)
    # ------------------------------------------------------------------ #

    def emit_run_start(
        self,
        agent_names: list[str],
        model_id: str,
        world_seed: Optional[int],
        width: int,
        height: int,
        max_ticks: int,
    ):
        """Emit run_start as the first event (tick=0, sim_time=None)."""
        self._emit("run_start", 0, {
            "config": {
                "width": width,
                "height": height,
                "max_ticks": max_ticks,
                "agent_count": len(agent_names),
                "agent_names": agent_names,
            },
            "model_id": model_id,
            "world_seed": world_seed,
        })

    def emit_agent_decision(
        self,
        tick: int,
        agent_name: str,
        action: dict,
        parse_ok: bool,
    ):
        """Emit after agent.decide_action(). action must have _llm_trace stripped."""
        action_name = action.get("action", "none")
        self._emit("agent_decision", tick, {
            "parsed_action": action,
            "parse_ok": parse_ok,
            "action_origin": self._action_origin(action_name),
        }, agent_id=agent_name)

    def emit_oracle_resolution(self, tick: int, agent_name: str, result: dict):
        """Emit after oracle.resolve_action(). Normalises missing effect keys to 0."""
        effects = result.get("effects", {})
        self._emit("oracle_resolution", tick, {
            "success": result["success"],
            "effects": {
                "hunger": effects.get("hunger", 0),
                "energy": effects.get("energy", 0),
                "life": effects.get("life", 0),
            },
        }, agent_id=agent_name)

    def emit_agent_state(self, tick: int, agent):
        """Emit after agent.apply_tick_effects(). Captures final post-tick state."""
        self._emit("agent_state", tick, {
            "life": agent.life,
            "hunger": agent.hunger,
            "energy": agent.energy,
            "pos": [agent.x, agent.y],
            "alive": agent.alive,
            "inventory": dict(agent.inventory.items),
        }, agent_id=agent.name)

    def emit_run_end(self, tick: int, survivors: list[str], total_ticks: int):
        """Emit run_end as the last event before close()."""
        self._emit("run_end", tick, {
            "survivors": survivors,
            "total_ticks": total_ticks,
        })

    def close(self):
        """Flush and close the events.jsonl file handle. Safe to call twice."""
        if self._fh and not self._fh.closed:
            self._fh.close()
