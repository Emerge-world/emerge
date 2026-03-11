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


class TestPhaseSegmentation:
    def test_pure_exploration_gives_one_phase(self):
        """10 ticks of exploration-only actions → single exploration phase."""
        events = []
        for t in range(1, 11):
            events.append(_decision(t, "move", reason="exploring unknown area"))
            events.append(_state(t))
            events.append(_perception(t))
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        assert len(result.phases) == 1
        assert result.phases[0].mode == "exploration"

    def test_innovation_burst_creates_phase_from_single_tick(self):
        """A single tick with innovation_attempt creates an innovation phase."""
        events = []
        for t in range(1, 6):
            events.append(_decision(t, "move", reason="exploring"))
            events.append(_state(t))
            events.append(_perception(t))
        # Tick 6: innovation attempt — should become its own phase
        events.append(_decision(6, "innovate"))
        events.append(_innovation_attempt(6))
        events.append(_state(6))
        events.append(_perception(6))
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        innovation_phases = [p for p in result.phases if p.mode == "innovation"]
        assert len(innovation_phases) >= 1
        assert any(p.tick_start <= 6 <= p.tick_end for p in innovation_phases)

    def test_night_rest_creates_maintenance_phase(self):
        """Sustained night + rest → maintenance phase appears."""
        events = []
        for t in range(1, 8):
            events.append(_decision(t, "rest"))
            events.append(_state(t, energy=25))
            events.append(_perception(t, night=True))
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        assert any(p.mode == "maintenance" for p in result.phases)

    def test_phases_cover_all_ticks_exactly(self):
        """Every tick in the run must be covered by exactly one phase (no gaps, no overlap)."""
        events = []
        for t in range(1, 15):
            action = "eat" if t % 3 == 0 else "move"
            events.append(_decision(t, action, reason="exploring"))
            events.append(_state(t))
            events.append(_perception(t))
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        covered_ticks: list[int] = []
        for phase in result.phases:
            for t in range(phase.tick_start, phase.tick_end + 1):
                covered_ticks.append(t)
        # No duplicates (no overlap)
        assert len(covered_ticks) == len(set(covered_ticks)), "Phases overlap"
        # All ticks covered (no gap)
        assert set(covered_ticks) == set(range(1, 15)), "Not all ticks covered"

    def test_phase_confidence_is_between_0_and_1(self):
        """All phase confidence values must be in [0, 1]."""
        events = []
        for t in range(1, 10):
            events.append(_decision(t, "eat"))
            events.append(_state(t))
            events.append(_perception(t))
        seg = BehaviorSegmenter()
        result = seg.segment("Ada", events)
        for phase in result.phases:
            assert 0.0 <= phase.confidence <= 1.0

    def test_segmentation_result_has_correct_agent_id(self):
        events = [_decision(1, "eat"), _state(1), _perception(1)]
        seg = BehaviorSegmenter()
        result = seg.segment("Bruno", events)
        assert result.agent_id == "Bruno"
        for phase in result.phases:
            assert phase.agent_id == "Bruno"
