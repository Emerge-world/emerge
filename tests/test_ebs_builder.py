"""Unit tests for simulation/ebs_builder.py — EBS computation, structural novelty classifier,
and contradiction detector."""

import json
from pathlib import Path

import pytest

from simulation.ebs_builder import (
    EBSBuilder,
    _classify_structural_novelty,
    _classify_dependency_depth,
    _check_contradiction,
)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _write_events(run_dir: Path, events: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(json.dumps(e) for e in events) + "\n"
    (run_dir / "events.jsonl").write_text(lines, encoding="utf-8")


def _run_start(run_id: str = "test") -> dict:
    return {
        "run_id": run_id, "tick": 0, "event_type": "run_start", "agent_id": None,
        "payload": {"config": {"agent_names": ["Ada"]}, "model_id": "test", "world_seed": 1},
    }


def _agent_state(tick: int, agent: str = "Ada", hunger: float = 20, energy: float = 80, life: float = 100) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_state", "agent_id": agent,
        "payload": {"hunger": hunger, "energy": energy, "life": life, "alive": True},
    }


def _agent_perception(tick: int, agent: str = "Ada", hunger: float = 20,
                      resources_nearby: list | None = None) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_perception", "agent_id": agent,
        "payload": {
            "pos": {"x": 0, "y": 0}, "hunger": hunger, "energy": 80, "life": 100,
            "resources_nearby": resources_nearby or [],
        },
    }


def _agent_decision(tick: int, agent: str = "Ada", action: str = "move",
                    direction: str = "", parse_ok: bool = True) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_decision", "agent_id": agent,
        "payload": {"parsed_action": {"action": action, "direction": direction}, "parse_ok": parse_ok},
    }


def _oracle_resolution(tick: int, agent: str = "Ada", success: bool = True,
                       action: str = "move", resource: str | None = None) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "oracle_resolution", "agent_id": agent,
        "payload": {"success": success, "action": action, "resource": resource,
                    "effects": {"hunger": 0, "energy": 0, "life": 0}},
    }


def _innovation_attempt(tick: int, agent: str = "Ada") -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "innovation_attempt", "agent_id": agent,
        "payload": {"name": "gather_stone", "description": "pick up stone"},
    }


def _innovation_validated(tick: int, agent: str = "Ada", name: str = "gather_stone",
                          approved: bool = True, category: str = "CRAFTING",
                          requires: dict | None = None, produces: dict | None = None) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "innovation_validated", "agent_id": agent,
        "payload": {
            "name": name, "approved": approved, "category": category,
            "reason_code": "INNOVATION_APPROVED" if approved else "INNOVATION_REJECTED",
            "requires": requires or {"tile": "cave"},
            "produces": produces or {"stone": 1},
        },
    }


def _custom_action_executed(tick: int, agent: str = "Ada",
                             name: str = "gather_stone", success: bool = True) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "custom_action_executed", "agent_id": agent,
        "payload": {"name": name, "success": success, "effects": {"hunger": 0, "energy": -5, "life": 0}},
    }


def _memory_compression(tick: int, agent: str = "Ada", learnings: list[str] | None = None) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "memory_compression_result", "agent_id": agent,
        "payload": {"episode_count": 5, "learnings": learnings or []},
    }


def _run_end(tick: int = 10) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "run_end", "agent_id": None,
        "payload": {"survivors": ["Ada"], "total_ticks": tick},
    }


# ------------------------------------------------------------------ #
# Structural novelty classifier
# ------------------------------------------------------------------ #

class TestStructuralNoveltyClassifier:
    def test_inventory_enabler(self):
        tag = _classify_structural_novelty(
            requires={"tile": "cave"},
            produces={"stone": 1},
            description="pick up stone from cave",
        )
        assert tag == "inventory_enabler"

    def test_recipe_action(self):
        tag = _classify_structural_novelty(
            requires={"items": {"stone": 2, "wood": 1}},
            produces={"axe": 1},
            description="craft axe from stone and wood",
        )
        assert tag == "recipe_action"

    def test_world_modifying(self):
        tag = _classify_structural_novelty(
            requires={"tile": "forest"},
            produces={"tile": "cleared"},
            description="clear a forest tile",
        )
        assert tag == "world_modifying"

    def test_coordination_action_from_description(self):
        tag = _classify_structural_novelty(
            requires={},
            produces={},
            description="teach another agent how to find food",
        )
        assert tag == "coordination_action"

    def test_base_extension_fallback(self):
        tag = _classify_structural_novelty(
            requires={"min_energy": 10},
            produces={"energy": 5},
            description="meditate to recover energy",
        )
        assert tag == "base_extension"

    def test_none_requires_produces(self):
        tag = _classify_structural_novelty(requires=None, produces=None, description="")
        assert tag == "base_extension"


# ------------------------------------------------------------------ #
# Dependency depth classifier
# ------------------------------------------------------------------ #

class TestDependencyDepth:
    def test_depth_0_empty_requires(self):
        assert _classify_dependency_depth({}, set()) == 0

    def test_depth_0_only_energy(self):
        assert _classify_dependency_depth({"min_energy": 5}, set()) == 0

    def test_depth_1_tile_only(self):
        assert _classify_dependency_depth({"tile": "forest"}, set()) == 1

    def test_depth_2_items(self):
        assert _classify_dependency_depth({"items": {"wood": 1}}, set()) == 2

    def test_depth_3_requires_prior_innovation(self):
        assert _classify_dependency_depth({"items": {"axe": 1}}, {"axe"}) == 3

    def test_depth_0_none(self):
        assert _classify_dependency_depth(None, set()) == 0


# ------------------------------------------------------------------ #
# Contradiction detector
# ------------------------------------------------------------------ #

class TestContradictionDetector:
    def test_no_fruit_contradicts_confirmed_fruit(self):
        assert _check_contradiction("no fruit here", {"fruit"}, set()) is True

    def test_fruit_not_found_contradicts(self):
        assert _check_contradiction("fruit not found", {"fruit"}, set()) is True

    def test_consistent_learning_not_flagged(self):
        assert _check_contradiction("fruit restores hunger", {"fruit"}, set()) is False

    def test_action_never_works_contradicts_succeeded(self):
        assert _check_contradiction("eat never works here", set(), {"eat"}) is True

    def test_unknown_resource_not_flagged(self):
        assert _check_contradiction("no mushrooms", {"fruit"}, set()) is False

    def test_empty_learning(self):
        assert _check_contradiction("", {"fruit"}, {"eat"}) is False


# ------------------------------------------------------------------ #
# EBSBuilder — no events / missing file
# ------------------------------------------------------------------ #

class TestEBSBuilderEdgeCases:
    def test_no_events_file(self, tmp_path):
        """build() is a no-op when events.jsonl is missing."""
        EBSBuilder(tmp_path).build()
        assert not (tmp_path / "metrics" / "ebs.json").exists()

    def test_zero_innovations(self, tmp_path):
        """All EBS scores default to 0 gracefully when no innovations occur."""
        events = [_run_start(), _agent_decision(1), _oracle_resolution(1), _agent_state(1), _run_end()]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        ebs_data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert 0.0 <= ebs_data["ebs"] <= 100.0
        assert ebs_data["components"]["novelty"]["sub_scores"]["approval_rate"] == 0.0
        assert ebs_data["innovations"] == []

    def test_empty_events_file(self, tmp_path):
        """build() handles completely empty events.jsonl without crashing.
        Stability defaults to 100 (no failures), contributing 15 pts → ebs == 15.0."""
        (tmp_path / "events.jsonl").write_text("", encoding="utf-8")
        EBSBuilder(tmp_path).build()
        ebs_data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert 0.0 <= ebs_data["ebs"] <= 100.0
        assert ebs_data["components"]["novelty"]["sub_scores"]["approval_rate"] == 0.0


# ------------------------------------------------------------------ #
# EBSBuilder — Novelty component
# ------------------------------------------------------------------ #

class TestNoveltyComponent:
    def test_one_approved_innovation_increases_novelty(self, tmp_path):
        events = [
            _run_start(),
            _innovation_attempt(1),
            _innovation_validated(1, approved=True, category="CRAFTING",
                                   requires={"tile": "cave"}, produces={"stone": 1}),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        novelty = data["components"]["novelty"]
        assert novelty["sub_scores"]["approval_rate"] == 1.0
        assert novelty["score"] > 0.0

    def test_rejected_innovation_zero_approval_rate(self, tmp_path):
        events = [
            _run_start(),
            _innovation_attempt(1),
            _innovation_validated(1, approved=False),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["novelty"]["sub_scores"]["approval_rate"] == 0.0

    def test_category_diversity(self, tmp_path):
        """Two different categories → diversity = 2/4 = 0.5."""
        events = [
            _run_start(),
            _innovation_attempt(1), _innovation_validated(1, name="a", category="CRAFTING",
                                                           requires={"tile": "x"}, produces={"stone": 1}),
            _innovation_attempt(2), _innovation_validated(2, name="b", category="SURVIVAL",
                                                           requires={"min_energy": 5}, produces={"energy": 5}),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["novelty"]["sub_scores"]["category_diversity"] == pytest.approx(0.5)

    def test_structural_originality_non_base(self, tmp_path):
        """inventory_enabler counts as structurally original."""
        events = [
            _run_start(),
            _innovation_attempt(1),
            _innovation_validated(1, requires={"tile": "cave"}, produces={"stone": 1}),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["novelty"]["sub_scores"]["structural_originality"] == 1.0
        assert data["innovations"][0]["structural_novelty"] == "inventory_enabler"


# ------------------------------------------------------------------ #
# EBSBuilder — Realization component
# ------------------------------------------------------------------ #

class TestRealizationComponent:
    def test_used_innovation_increases_realization(self, tmp_path):
        events = [
            _run_start(),
            _innovation_attempt(1),
            _innovation_validated(1),
            _custom_action_executed(3, success=True),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        real = data["components"]["realization"]
        assert real["sub_scores"]["use_rate"] == 1.0
        assert real["sub_scores"]["success_rate"] == 1.0
        assert real["score"] == pytest.approx(100.0)

    def test_unused_innovation_zero_use_rate(self, tmp_path):
        events = [
            _run_start(),
            _innovation_attempt(1),
            _innovation_validated(1),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["realization"]["sub_scores"]["use_rate"] == 0.0


# ------------------------------------------------------------------ #
# EBSBuilder — Stability component
# ------------------------------------------------------------------ #

class TestStabilityComponent:
    def test_high_parse_fail_rate_lowers_stability(self, tmp_path):
        events = [
            _run_start(),
            _agent_decision(1, parse_ok=False),
            _agent_decision(2, parse_ok=False),
            _agent_decision(3, parse_ok=True),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        stability = data["components"]["stability"]
        assert stability["sub_scores"]["invalid_action_rate"] == pytest.approx(2 / 3, abs=1e-3)
        assert stability["score"] < 100.0

    def test_contradiction_in_learnings_lowers_stability(self, tmp_path):
        events = [
            _run_start(),
            # Establish ground truth: fruit was successfully eaten
            _oracle_resolution(1, success=True, action="eat", resource="fruit"),
            # Learning contradicts this
            _memory_compression(5, learnings=["no fruit exists in this world"]),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        stability = data["components"]["stability"]
        assert stability["sub_scores"]["false_knowledge_rate"] > 0.0
        assert stability["score"] < 100.0

    def test_no_parse_fails_no_contradictions_full_stability(self, tmp_path):
        events = [
            _run_start(),
            _agent_decision(1, parse_ok=True),
            _memory_compression(5, learnings=["fruit restores hunger"]),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["stability"]["score"] == pytest.approx(100.0)


# ------------------------------------------------------------------ #
# EBSBuilder — Autonomy component (proactive join)
# ------------------------------------------------------------------ #

class TestAutonomyComponent:
    def test_proactive_move_toward_resource(self, tmp_path):
        """Agent moves east while hunger < 60 AND fruit is to the east → proactive."""
        events = [
            _run_start(),
            _agent_perception(1, hunger=30, resources_nearby=[{"type": "fruit", "tile": "forest", "dx": 1, "dy": 0}]),
            _agent_decision(1, action="move", direction="east"),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["autonomy"]["sub_scores"]["proactive_resource_acquisition"] == 1.0

    def test_hungry_move_not_proactive(self, tmp_path):
        """Agent moves east while hunger >= 60 → reactive, not proactive."""
        events = [
            _run_start(),
            _agent_perception(1, hunger=75, resources_nearby=[{"type": "fruit", "tile": "forest", "dx": 1, "dy": 0}]),
            _agent_decision(1, action="move", direction="east"),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["autonomy"]["sub_scores"]["proactive_resource_acquisition"] == 0.0

    def test_move_away_from_resource_not_proactive(self, tmp_path):
        """Agent moves west while resource is to the east → not proactive."""
        events = [
            _run_start(),
            _agent_perception(1, hunger=20, resources_nearby=[{"type": "fruit", "tile": "forest", "dx": 1, "dy": 0}]),
            _agent_decision(1, action="move", direction="west"),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["autonomy"]["sub_scores"]["proactive_resource_acquisition"] == 0.0

    def test_self_generated_subgoals_still_zero_without_planning_events(self, tmp_path):
        events = [_run_start(), _run_end()]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["autonomy"]["sub_scores"]["self_generated_subgoals"] == 0.0

    def test_self_generated_subgoals_uses_planning_events(self, tmp_path):
        events = [
            _run_start(),
            _agent_decision(1, action="move", direction="east"),
            {
                "run_id": "test",
                "tick": 1,
                "event_type": "plan_created",
                "agent_id": "Ada",
                "payload": {"goal": "stabilize food", "subgoal_count": 2},
            },
            {
                "run_id": "test",
                "tick": 2,
                "event_type": "subgoal_completed",
                "agent_id": "Ada",
                "payload": {"description": "move toward fruit"},
            },
            {
                "run_id": "test",
                "tick": 3,
                "event_type": "subgoal_completed",
                "agent_id": "Ada",
                "payload": {"description": "eat fruit"},
            },
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert data["components"]["autonomy"]["sub_scores"]["self_generated_subgoals"] > 0.0


# ------------------------------------------------------------------ #
# EBSBuilder — output schema
# ------------------------------------------------------------------ #

class TestOutputSchema:
    def test_ebs_in_range(self, tmp_path):
        events = [_run_start(), _run_end()]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        assert 0.0 <= data["ebs"] <= 100.0

    def test_all_components_present(self, tmp_path):
        events = [_run_start(), _run_end()]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        for key in ("novelty", "utility", "realization", "stability", "autonomy"):
            assert key in data["components"]
        assert "innovations" in data

    def test_innovation_entry_has_structural_fields(self, tmp_path):
        events = [
            _run_start(),
            _innovation_attempt(1),
            _innovation_validated(1, requires={"tile": "cave"}, produces={"stone": 1}),
            _run_end(),
        ]
        _write_events(tmp_path, events)
        EBSBuilder(tmp_path).build()
        data = json.loads((tmp_path / "metrics" / "ebs.json").read_text())
        inv = data["innovations"][0]
        assert "structural_novelty" in inv
        assert "dependency_depth" in inv
        assert inv["dependency_depth"] == 1
