"""Tests for AnomalyDetector."""

import pytest
from simulation.digest.anomaly_detector import AnomalyDetector, Anomaly


def _decision(tick: int, agent: str = "Ada", action: str = "move", parse_ok: bool = True) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "agent_decision", "agent_id": agent,
        "payload": {"parsed_action": {"action": action}, "parse_ok": parse_ok},
    }


def _oracle(tick: int, agent: str = "Ada", action: str = "move", success: bool = True,
            cache_hit: bool = True, is_innovate: bool = False) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "oracle_resolution", "agent_id": agent,
        "payload": {"success": success, "action": action, "cache_hit": cache_hit,
                    "is_innovation_action": is_innovate, "effects": {}},
    }


def _memory(tick: int, agent: str = "Ada", learnings: list | None = None) -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "memory_compression_result",
        "agent_id": agent, "payload": {"learnings": learnings or [], "episode_count": 3},
    }


def _oracle_consume(tick: int, agent: str = "Ada", resource: str = "fruit") -> dict:
    return {
        "run_id": "test", "tick": tick, "event_type": "oracle_resolution", "agent_id": agent,
        "payload": {"success": True, "action": "eat", "resource": resource,
                    "cache_hit": True, "effects": {"hunger": -20}},
    }


class TestParseFailStreaks:
    def test_three_consecutive_parse_fails_creates_streak(self):
        events = [
            _decision(1, parse_ok=False),
            _decision(2, parse_ok=False),
            _decision(3, parse_ok=False),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        streak = [a for a in anomalies if a.type == "PARSE_FAIL_STREAK"]
        assert len(streak) >= 1
        assert streak[0].severity == "high"
        assert streak[0].agent_id == "Ada"

    def test_two_parse_fails_no_streak(self):
        events = [_decision(1, parse_ok=False), _decision(2, parse_ok=False)]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert not any(a.type == "PARSE_FAIL_STREAK" for a in anomalies)

    def test_broken_streak_resets_counter(self):
        events = [
            _decision(1, parse_ok=False),
            _decision(2, parse_ok=False),
            _decision(3, parse_ok=True),   # breaks streak
            _decision(4, parse_ok=False),
            _decision(5, parse_ok=False),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert not any(a.type == "PARSE_FAIL_STREAK" for a in anomalies)


class TestRepeatedFailures:
    def test_same_action_fails_three_times_in_ten_ticks(self):
        events = [
            _oracle(1, action="move_north", success=False),
            _oracle(5, action="move_north", success=False),
            _oracle(9, action="move_north", success=False),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        repeated = [a for a in anomalies if a.type == "REPEATED_FAILURE"]
        assert len(repeated) >= 1
        assert repeated[0].severity == "medium"

    def test_three_failures_spread_over_more_than_ten_ticks_no_anomaly(self):
        events = [
            _oracle(1, action="move_north", success=False),
            _oracle(6, action="move_north", success=False),
            _oracle(12, action="move_north", success=False),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert not any(a.type == "REPEATED_FAILURE" for a in anomalies)


class TestContradictions:
    def test_learning_contradicts_confirmed_resource(self):
        events = [
            _oracle_consume(5, resource="fruit"),  # confirms fruit exists
            _memory(20, learnings=["no fruit can be found anywhere"]),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        contradictions = [a for a in anomalies if a.type == "CONTRADICTION"]
        assert len(contradictions) >= 1
        assert contradictions[0].severity == "high"

    def test_non_contradicting_learning_no_anomaly(self):
        events = [
            _oracle_consume(5, resource="fruit"),
            _memory(20, learnings=["fruit is available near trees"]),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert not any(a.type == "CONTRADICTION" for a in anomalies)


class TestUnusualPrecedent:
    def test_new_oracle_precedent_on_innovate_action(self):
        events = [
            _oracle(10, action="craft_stick", cache_hit=False, is_innovate=True),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        precedent = [a for a in anomalies if a.type == "UNUSUAL_PRECEDENT"]
        assert len(precedent) == 1
        assert precedent[0].severity == "low"

    def test_cache_miss_on_normal_action_not_flagged(self):
        events = [
            _oracle(10, action="move", cache_hit=False, is_innovate=False),
        ]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert not any(a.type == "UNUSUAL_PRECEDENT" for a in anomalies)


class TestAnomalyStructure:
    def test_anomaly_has_required_fields(self):
        events = [_decision(1, parse_ok=False), _decision(2, parse_ok=False), _decision(3, parse_ok=False)]
        detector = AnomalyDetector()
        anomalies = detector.detect(events)
        assert len(anomalies) > 0
        a = anomalies[0]
        assert a.anomaly_id
        assert a.type
        assert a.severity in ("high", "medium", "low")
        assert isinstance(a.tick, int)
        assert isinstance(a.supporting_event_ids, list)
        assert isinstance(a.description, str)
