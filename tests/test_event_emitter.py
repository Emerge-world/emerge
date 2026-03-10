"""Tests for simulation/event_emitter.py."""

import json
from unittest.mock import MagicMock

import pytest

from simulation.config import BASE_ACTIONS
from simulation.day_cycle import DayCycle
from simulation.event_emitter import EventEmitter


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_emitter(tmp_path, monkeypatch, run_id="test-run-1234", seed=42):
    monkeypatch.chdir(tmp_path)
    day_cycle = DayCycle(start_hour=6)
    em = EventEmitter(
        run_id=run_id,
        seed=seed,
        world_width=15,
        world_height=15,
        max_ticks=72,
        agent_count=3,
        agent_names=["Ada", "Bruno", "Clara"],
        model_id="test-model",
        day_cycle=day_cycle,
    )
    return em


def _mock_agent(name="Ada", life=100.0, hunger=5.0, energy=90.0, x=3, y=4, alive=True, inventory=None):
    agent = MagicMock()
    agent.name = name
    agent.life = life
    agent.hunger = hunger
    agent.energy = energy
    agent.x = x
    agent.y = y
    agent.alive = alive
    agent.inventory.items = inventory or {}
    return agent


def _read_events(tmp_path, run_id="test-run-1234") -> list[dict]:
    path = tmp_path / "data" / "runs" / run_id / "events.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line]


# ------------------------------------------------------------------ #
# meta.json
# ------------------------------------------------------------------ #

class TestMeta:
    def test_meta_json_created(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.close()
        meta_path = tmp_path / "data" / "runs" / "test-run-1234" / "meta.json"
        assert meta_path.exists()

    def test_meta_json_fields(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch, seed=99)
        em.close()
        meta = json.loads((tmp_path / "data" / "runs" / "test-run-1234" / "meta.json").read_text())
        assert meta["run_id"] == "test-run-1234"
        assert meta["seed"] == 99
        assert meta["width"] == 15
        assert meta["height"] == 15
        assert meta["max_ticks"] == 72
        assert meta["agent_count"] == 3
        assert meta["agent_names"] == ["Ada", "Bruno", "Clara"]
        assert meta["model_id"] == "test-model"
        assert "created_at" in meta

    def test_events_jsonl_created(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.close()
        assert (tmp_path / "data" / "runs" / "test-run-1234" / "events.jsonl").exists()

    def test_meta_created_before_events(self, tmp_path, monkeypatch):
        """meta.json must exist even if the process crashes before any events."""
        em = _make_emitter(tmp_path, monkeypatch)
        # Don't emit anything — meta should still be there
        meta_path = tmp_path / "data" / "runs" / "test-run-1234" / "meta.json"
        assert meta_path.exists()
        em.close()


# ------------------------------------------------------------------ #
# run_start
# ------------------------------------------------------------------ #

class TestRunStart:
    def test_emits_one_line(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada", "Bruno"], "m", 42, 15, 15, 72)
        em.close()
        events = _read_events(tmp_path)
        assert len(events) == 1

    def test_event_type(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada"], "m", None, 10, 10, 50)
        em.close()
        assert _read_events(tmp_path)[0]["event_type"] == "run_start"

    def test_tick_zero_sim_time_null(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada"], "m", None, 10, 10, 50)
        em.close()
        ev = _read_events(tmp_path)[0]
        assert ev["tick"] == 0
        assert ev["sim_time"] is None

    def test_agent_id_null(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada"], "m", None, 10, 10, 50)
        em.close()
        assert _read_events(tmp_path)[0]["agent_id"] is None

    def test_payload_fields(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada", "Bruno"], "my-model", 7, 20, 20, 100)
        em.close()
        p = _read_events(tmp_path)[0]["payload"]
        assert p["config"]["width"] == 20
        assert p["config"]["agent_count"] == 2
        assert p["model_id"] == "my-model"
        assert p["world_seed"] == 7


# ------------------------------------------------------------------ #
# agent_decision
# ------------------------------------------------------------------ #

class TestAgentDecision:
    @pytest.mark.parametrize("base_action", BASE_ACTIONS)
    def test_base_action_origin(self, tmp_path, monkeypatch, base_action):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Ada", {"action": base_action}, parse_ok=True)
        em.close()
        ev = _read_events(tmp_path)[0]
        assert ev["payload"]["action_origin"] == "base"

    def test_innovation_action_origin(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Ada", {"action": "dance_with_wolves"}, parse_ok=True)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["action_origin"] == "innovation"

    def test_parse_ok_true(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Ada", {"action": "move"}, parse_ok=True)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["parse_ok"] is True

    def test_parse_ok_false(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Ada", {"action": "eat"}, parse_ok=False)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["parse_ok"] is False

    def test_parsed_action_in_payload(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        action = {"action": "move", "direction": "north", "reason": "explore"}
        em.emit_agent_decision(2, "Bruno", action, parse_ok=True)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["parsed_action"]["direction"] == "north"

    def test_agent_id_set(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Bruno", {"action": "eat"}, parse_ok=True)
        em.close()
        assert _read_events(tmp_path)[0]["agent_id"] == "Bruno"

    def test_sim_time_computed(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(1, "Ada", {"action": "move"}, parse_ok=True)
        em.close()
        # DayCycle(start_hour=6): tick=1 → hour=6, day=1
        st = _read_events(tmp_path)[0]["sim_time"]
        assert st == {"day": 1, "hour": 6}


# ------------------------------------------------------------------ #
# oracle_resolution
# ------------------------------------------------------------------ #

class TestOracleResolution:
    def test_success_true(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_oracle_resolution(1, "Ada", {"success": True, "effects": {"energy": -3}})
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["success"] is True

    def test_effects_normalized(self, tmp_path, monkeypatch):
        """Missing effect keys should default to 0."""
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_oracle_resolution(1, "Ada", {"success": True, "effects": {"energy": -3}})
        em.close()
        effects = _read_events(tmp_path)[0]["payload"]["effects"]
        assert effects["energy"] == -3
        assert effects["hunger"] == 0
        assert effects["life"] == 0

    def test_success_false(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_oracle_resolution(1, "Ada", {"success": False, "effects": {}})
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["success"] is False


# ------------------------------------------------------------------ #
# agent_state
# ------------------------------------------------------------------ #

class TestAgentState:
    def test_state_fields(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        agent = _mock_agent(life=95.0, hunger=20.0, energy=60.0, x=5, y=7, alive=True,
                             inventory={"fruit": 2})
        em.emit_agent_state(1, agent)
        em.close()
        p = _read_events(tmp_path)[0]["payload"]
        assert p["life"] == 95.0
        assert p["hunger"] == 20.0
        assert p["energy"] == 60.0
        assert p["pos"] == [5, 7]
        assert p["alive"] is True
        assert p["inventory"] == {"fruit": 2}

    def test_empty_inventory(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        agent = _mock_agent()
        em.emit_agent_state(1, agent)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["inventory"] == {}

    def test_dead_agent(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        agent = _mock_agent(life=0, alive=False)
        em.emit_agent_state(5, agent)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["alive"] is False


# ------------------------------------------------------------------ #
# run_end
# ------------------------------------------------------------------ #

class TestRunEnd:
    def test_event_type(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_end(10, ["Ada"], 10)
        em.close()
        assert _read_events(tmp_path)[0]["event_type"] == "run_end"

    def test_survivors(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_end(50, ["Ada", "Clara"], 50)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["survivors"] == ["Ada", "Clara"]

    def test_total_ticks(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_end(72, [], 72)
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["total_ticks"] == 72


# ------------------------------------------------------------------ #
# Integration / ordering
# ------------------------------------------------------------------ #

class TestIntegration:
    def test_full_sequence_ordering(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_run_start(["Ada"], "m", 1, 10, 10, 5)
        em.emit_agent_decision(1, "Ada", {"action": "move"}, parse_ok=True)
        em.emit_oracle_resolution(1, "Ada", {"success": True, "effects": {}})
        em.emit_agent_state(1, _mock_agent())
        em.emit_run_end(1, ["Ada"], 1)
        em.close()
        types = [e["event_type"] for e in _read_events(tmp_path)]
        assert types == ["run_start", "agent_decision", "oracle_resolution", "agent_state", "run_end"]

    def test_run_id_consistent(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch, run_id="my-run-abc")
        em.emit_run_start(["Ada"], "m", None, 10, 10, 5)
        em.emit_agent_decision(1, "Ada", {"action": "eat"}, parse_ok=True)
        em.emit_run_end(1, ["Ada"], 1)
        em.close()
        for ev in _read_events(tmp_path, run_id="my-run-abc"):
            assert ev["run_id"] == "my-run-abc"

    def test_close_idempotent(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.close()
        em.close()  # must not raise

    def test_sim_time_night(self, tmp_path, monkeypatch):
        """tick=16 with start_hour=6 → hour=21 (night)."""
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_agent_decision(16, "Ada", {"action": "rest"}, parse_ok=True)
        em.close()
        st = _read_events(tmp_path)[0]["sim_time"]
        assert st["hour"] == 21


# ------------------------------------------------------------------ #
# Innovation events
# ------------------------------------------------------------------ #

class TestInnovationEvents:
    def test_emit_innovation_attempt_event_type(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_innovation_attempt(3, "Ada", {
            "new_action_name": "gather_wood",
            "description": "Collect wood from trees",
            "requires": {"tile": "forest"},
            "produces": {"wood": 1},
        })
        em.close()
        ev = _read_events(tmp_path)[0]
        assert ev["event_type"] == "innovation_attempt"

    def test_emit_innovation_attempt_payload(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_innovation_attempt(3, "Ada", {
            "new_action_name": "gather_wood",
            "description": "Collect wood",
            "requires": {"tile": "forest"},
            "produces": {"wood": 1},
        })
        em.close()
        p = _read_events(tmp_path)[0]["payload"]
        assert p["name"] == "gather_wood"
        assert p["description"] == "Collect wood"
        assert p["requires"] == {"tile": "forest"}
        assert p["produces"] == {"wood": 1}

    def test_emit_innovation_attempt_agent_id(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_innovation_attempt(3, "Ada", {"new_action_name": "foo"})
        em.close()
        assert _read_events(tmp_path)[0]["agent_id"] == "Ada"

    def test_emit_innovation_validated_approved(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_innovation_validated(3, "Ada", {
            "success": True,
            "name": "gather_wood",
            "category": "CRAFTING",
            "reason_code": "INNOVATION_APPROVED",
            "effects": {"energy": -10, "new_action": "gather_wood"},
            "message": "ok",
        })
        em.close()
        p = _read_events(tmp_path)[0]["payload"]
        assert p["approved"] is True
        assert p["name"] == "gather_wood"
        assert p["category"] == "CRAFTING"
        assert p["reason_code"] == "INNOVATION_APPROVED"

    def test_emit_innovation_validated_rejected(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_innovation_validated(3, "Ada", {
            "success": False,
            "name": "fly",
            "category": None,
            "reason_code": "INNOVATION_REJECTED",
            "effects": {},
            "message": "nope",
        })
        em.close()
        p = _read_events(tmp_path)[0]["payload"]
        assert p["approved"] is False
        assert p["name"] == "fly"
        assert p["reason_code"] == "INNOVATION_REJECTED"

    def test_emit_custom_action_executed_success(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_custom_action_executed(5, "Ada",
            action={"action": "gather_wood"},
            result={"success": True, "effects": {"energy": -5}, "message": "done"},
        )
        em.close()
        p = _read_events(tmp_path)[0]["payload"]
        assert p["name"] == "gather_wood"
        assert p["success"] is True
        assert p["effects"]["energy"] == -5

    def test_emit_custom_action_executed_failure(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.emit_custom_action_executed(5, "Ada",
            action={"action": "gather_wood"},
            result={"success": False, "effects": {}, "message": "failed"},
        )
        em.close()
        assert _read_events(tmp_path)[0]["payload"]["success"] is False

    def test_run_dir_attribute(self, tmp_path, monkeypatch):
        em = _make_emitter(tmp_path, monkeypatch)
        em.close()
        assert em.run_dir.resolve() == (tmp_path / "data" / "runs" / "test-run-1234").resolve()
