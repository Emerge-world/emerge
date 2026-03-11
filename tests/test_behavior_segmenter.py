"""Tests for BehaviorSegmenter tick scoring."""

import pytest
from simulation.digest.behavior_segmenter import (
    BehaviorSegmenter,
    TickModeScore,
    PhaseSegment,
    AgentSegmentation,
)


def _decision(tick: int, action: str, direction: str = "", reason: str = "",
              agent: str = "Ada", parse_ok: bool = True) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_decision",
        "agent_id": agent,
        "payload": {
            "parsed_action": {"action": action, "direction": direction, "reason": reason},
            "parse_ok": parse_ok,
        },
    }


def _state(tick: int, energy: float = 80, agent: str = "Ada") -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_state",
        "agent_id": agent,
        "payload": {"energy": energy, "hunger": 20, "life": 100, "alive": True, "pos": {"x": 0, "y": 0}},
    }


def _perception(tick: int, hunger: float = 20, resources: list | None = None,
                agent: str = "Ada", night: bool = False) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_perception",
        "agent_id": agent,
        "payload": {
            "pos": {"x": 0, "y": 0}, "hunger": hunger, "energy": 80,
            "resources_nearby": resources or [],
            "night_penalty_active": night,
        },
    }


def _innovation_attempt(tick: int, agent: str = "Ada") -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "innovation_attempt",
        "agent_id": agent, "payload": {"name": "craft_stick", "description": "make a stick"},
    }


def _custom_action(tick: int, agent: str = "Ada") -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "custom_action_executed",
        "agent_id": agent, "payload": {"name": "craft_stick", "success": True},
    }


class TestTickScoring:
    def test_eat_action_scores_exploitation(self):
        events = [_decision(1, "eat"), _state(1), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["exploitation"] >= 5.0

    def test_rest_action_scores_maintenance(self):
        events = [_decision(1, "rest"), _state(1), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["maintenance"] >= 5.0

    def test_innovate_action_scores_innovation(self):
        events = [_decision(1, "innovate"), _state(1), _perception(1), _innovation_attempt(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["innovation"] >= 6.0

    def test_explore_reason_scores_exploration(self):
        events = [_decision(1, "move", reason="exploring the unknown area"), _state(1), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["exploration"] >= 3.0

    def test_night_penalty_boosts_maintenance(self):
        events = [_decision(1, "move"), _state(1), _perception(1, night=True)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["maintenance"] >= 2.0

    def test_low_energy_boosts_maintenance(self):
        events = [_decision(1, "move"), _state(1, energy=20), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.scores["maintenance"] >= 2.0

    def test_assigned_mode_is_highest_score(self):
        events = [_decision(1, "eat"), _state(1), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        tick1 = next(t for t in result.tick_scores if t.tick == 1)
        assert tick1.assigned_mode == "exploitation"
