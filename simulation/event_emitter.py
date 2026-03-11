"""
Canonical event emitter: writes an always-on JSONL event stream per run.

Output: data/runs/<run_id>/
  meta.json     — run config, model, seed, timestamp (written at init)
  events.jsonl  — one JSON object per line, the authoritative data source
  blobs/
    prompts/    — rendered prompts (system + user) for agent and oracle LLM calls
    llm_raw/    — raw LLM responses for agent and oracle calls
"""

import datetime
import hashlib
import json
import re
import subprocess
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
        agent_model_id: str,
        oracle_model_id: str,
        day_cycle: DayCycle,
        precedents_file: Optional[str] = None,
    ):
        self.run_id = run_id
        self.seed = seed
        self._day_cycle = day_cycle

        self.run_dir = Path("data") / "runs" / run_id
        run_dir = self.run_dir
        run_dir.mkdir(parents=True, exist_ok=True)

        # Create blob subdirectories
        (run_dir / "blobs" / "prompts").mkdir(parents=True, exist_ok=True)
        (run_dir / "blobs" / "llm_raw").mkdir(parents=True, exist_ok=True)

        # SHA-256 dedup map: sha256 hex → relative path string
        self._blob_sha_map: dict[str, str] = {}

        # Compute git commit hash
        try:
            git_commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            git_commit = "unknown"

        # Compute SHA-256 hashes of all prompt templates (skip old_system)
        prompts_dir = Path("prompts")
        prompt_hashes: dict[str, str] = {}
        if prompts_dir.is_dir():
            for f in sorted(prompts_dir.rglob("*.txt")):
                key = str(f.relative_to(prompts_dir).with_suffix(""))
                if key == "agent/old_system":
                    continue
                content = f.read_text(encoding="utf-8")
                prompt_hashes[key] = hashlib.sha256(content.encode()).hexdigest()

        # Write meta.json immediately so it's available even if the run crashes
        meta = {
            "run_id": run_id,
            "seed": seed,
            "width": world_width,
            "height": world_height,
            "max_ticks": max_ticks,
            "agent_count": agent_count,
            "agent_names": agent_names,
            "agent_model_id": agent_model_id,
            "oracle_model_id": oracle_model_id,
            "git_commit": git_commit,
            "prompt_hashes": prompt_hashes,
            "precedents_file": precedents_file,
            "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # Open events.jsonl with line-buffering so each write flushes automatically
        self._fh = (run_dir / "events.jsonl").open("w", encoding="utf-8", buffering=1)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _write_blob(self, subdir: str, name: str, content: str) -> tuple[str, str]:
        """Write content to blobs/{subdir}/{name}.txt with SHA-256 dedup.

        Returns (relative_path, sha256). If an identical blob already exists,
        returns the existing path without writing.
        """
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if sha in self._blob_sha_map:
            return self._blob_sha_map[sha], sha
        rel = f"blobs/{subdir}/{name}.txt"
        path = Path("data") / "runs" / self.run_id / rel
        path.write_text(content, encoding="utf-8")
        self._blob_sha_map[sha] = rel
        return rel, sha

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
        llm_trace: Optional[dict] = None,
    ):
        """Emit after agent.decide_action(). action must have _llm_trace stripped."""
        action_name = action.get("action", "none")
        payload: dict = {
            "parsed_action": action,
            "parse_ok": parse_ok,
            "action_origin": self._action_origin(action_name),
        }
        if llm_trace:
            combined_prompt = llm_trace["system_prompt"] + "\n\n---\n\n" + llm_trace["user_prompt"]
            p_ref, p_sha = self._write_blob("prompts", f"prompt_{tick}_{agent_name}", combined_prompt)
            r_ref, r_sha = self._write_blob("llm_raw", f"resp_{tick}_{agent_name}", llm_trace["raw_response"])
            payload["prompt_ref"] = p_ref
            payload["prompt_sha256"] = p_sha
            payload["raw_response_ref"] = r_ref
            payload["response_sha256"] = r_sha
        self._emit("agent_decision", tick, payload, agent_id=agent_name)

    def emit_oracle_resolution(
        self,
        tick: int,
        agent_name: str,
        result: dict,
        llm_trace: Optional[dict] = None,
        oracle_context: Optional[str] = None,
        cache_hit: bool = True,
    ):
        """Emit after oracle.resolve_action(). Normalises missing effect keys to 0."""
        effects = result.get("effects", {})
        payload: dict = {
            "success": result["success"],
            "effects": {
                "hunger": effects.get("hunger", 0),
                "energy": effects.get("energy", 0),
                "life": effects.get("life", 0),
            },
            "cache_hit": cache_hit,
            "prompt_ref": None,
            "prompt_sha256": None,
            "raw_response_ref": None,
            "response_sha256": None,
        }
        if llm_trace and oracle_context:
            safe_ctx = re.sub(r'[^a-zA-Z0-9_]', '_', oracle_context)[:40]
            combined_prompt = llm_trace["system_prompt"] + "\n\n---\n\n" + llm_trace["user_prompt"]
            p_ref, p_sha = self._write_blob("prompts", f"oracle_{tick}_{safe_ctx}", combined_prompt)
            r_ref, r_sha = self._write_blob("llm_raw", f"oracle_resp_{tick}_{safe_ctx}", llm_trace["raw_response"])
            payload["prompt_ref"] = p_ref
            payload["prompt_sha256"] = p_sha
            payload["raw_response_ref"] = r_ref
            payload["response_sha256"] = r_sha
        self._emit("oracle_resolution", tick, payload, agent_id=agent_name)

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

    def emit_agent_perception(
        self, tick: int, agent_name: str, *, pos: dict, hunger: float, energy: float,
        life: float, resources_nearby: list
    ):
        """Emit pre-decision perception snapshot (used by EBSBuilder for Autonomy scoring)."""
        self._emit("agent_perception", tick, {
            "pos": pos,
            "hunger": hunger,
            "energy": energy,
            "life": life,
            "resources_nearby": resources_nearby,
        }, agent_id=agent_name)

    def emit_memory_compression_result(
        self, tick: int, agent_name: str, *, episode_count: int, learnings: list[str]
    ):
        """Emit after memory compression (used by EBSBuilder for Stability scoring)."""
        self._emit("memory_compression_result", tick, {
            "episode_count": episode_count,
            "learnings": learnings,
        }, agent_id=agent_name)

    def emit_innovation_attempt(self, tick: int, agent_name: str, action: dict):
        """Emit before oracle validates an innovate action."""
        self._emit("innovation_attempt", tick, {
            "name": action.get("new_action_name", ""),
            "description": action.get("description", ""),
            "requires": action.get("requires"),
            "produces": action.get("produces"),
        }, agent_id=agent_name)

    def emit_innovation_validated(
        self, tick: int, agent_name: str, result: dict, *, requires=None, produces=None
    ):
        """Emit after oracle approves or rejects an innovate action."""
        self._emit("innovation_validated", tick, {
            "name": result.get("name", ""),
            "approved": result["success"],
            "category": result.get("category"),
            "reason_code": result.get("reason_code", "INNOVATION_APPROVED" if result["success"] else "INNOVATION_REJECTED"),
            "requires": requires,
            "produces": produces,
        }, agent_id=agent_name)

    def emit_custom_action_executed(self, tick: int, agent_name: str, action: dict, result: dict):
        """Emit when an agent uses a previously approved innovation."""
        effects = result.get("effects", {})
        self._emit("custom_action_executed", tick, {
            "name": action.get("action", ""),
            "success": result["success"],
            "effects": {
                "hunger": effects.get("hunger", 0),
                "energy": effects.get("energy", 0),
                "life": effects.get("life", 0),
            },
        }, agent_id=agent_name)

    def close(self):
        """Flush and close the events.jsonl file handle. Safe to call twice."""
        if self._fh and not self._fh.closed:
            self._fh.close()
