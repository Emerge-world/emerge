"""Tests for the subgoal completion/failure evaluator."""
from unittest.mock import MagicMock

from simulation.planning_state import PlanningSubgoal
from simulation.subgoal_evaluator import check_completion, check_failure


def _subgoal(completion_signal: str, failure_signal: str = "", kind: str = "move") -> PlanningSubgoal:
    return PlanningSubgoal(
        description="test subgoal",
        kind=kind,
        completion_signal=completion_signal,
        failure_signal=failure_signal,
    )


def _agent(hunger: int = 50, energy: int = 70, life: int = 100, inventory: dict | None = None):
    agent = MagicMock()
    agent.hunger = hunger
    agent.energy = energy
    agent.life = life
    agent.inventory = MagicMock()
    inv = inventory or {}
    agent.inventory.has.side_effect = lambda item, qty=1: inv.get(item, 0) >= qty
    agent.inventory.items = inv
    return agent


def _ok():
    return {"success": True}


def _fail():
    return {"success": False}


class TestNumericStateConditions:
    def test_hunger_below_threshold(self):
        sg = _subgoal("hunger < 30")
        assert check_completion(sg, _agent(hunger=25), _ok(), "eat")

    def test_hunger_not_below_threshold(self):
        sg = _subgoal("hunger < 30")
        assert not check_completion(sg, _agent(hunger=40), _ok(), "eat")

    def test_energy_above_threshold(self):
        sg = _subgoal("energy > 70")
        assert check_completion(sg, _agent(energy=80), _ok(), "rest")

    def test_energy_not_above_threshold(self):
        sg = _subgoal("energy > 70")
        assert not check_completion(sg, _agent(energy=60), _ok(), "rest")

    def test_life_condition(self):
        sg = _subgoal("life >= 80")
        assert check_completion(sg, _agent(life=90), _ok(), "rest")

    def test_numeric_independent_of_oracle_success(self):
        """State-based checks fire even when oracle failed."""
        sg = _subgoal("hunger < 30")
        assert check_completion(sg, _agent(hunger=10), _fail(), "move")


class TestInventoryConditions:
    def test_has_item(self):
        sg = _subgoal("has fruit in inventory")
        assert check_completion(sg, _agent(inventory={"fruit": 2}), _ok(), "pickup")

    def test_missing_item(self):
        sg = _subgoal("has stone in inventory")
        assert not check_completion(sg, _agent(inventory={"fruit": 1}), _ok(), "pickup")

    def test_inventory_has_with_quantity(self):
        sg = _subgoal("inventory has 2 stone")
        assert check_completion(sg, _agent(inventory={"stone": 3}), _ok(), "pickup")

    def test_quantity_not_met(self):
        sg = _subgoal("inventory has 3 stone")
        assert not check_completion(sg, _agent(inventory={"stone": 2}), _ok(), "pickup")


class TestActionSignalKeywords:
    def test_eat_matches_food_signal(self):
        sg = _subgoal("ate food and satisfied hunger")
        assert check_completion(sg, _agent(hunger=60), _ok(), "eat")

    def test_eat_no_match_on_failure(self):
        sg = _subgoal("ate food successfully")
        assert not check_completion(sg, _agent(), _fail(), "eat")

    def test_rest_matches_energy_signal(self):
        sg = _subgoal("energy restored after resting")
        assert check_completion(sg, _agent(), _ok(), "rest")

    def test_pickup_matches_gather_signal(self):
        sg = _subgoal("gathered resources from tile")
        assert check_completion(sg, _agent(), _ok(), "pickup")

    def test_move_matches_reach_signal(self):
        sg = _subgoal("reached the fruit tree")
        assert check_completion(sg, _agent(), _ok(), "move")

    def test_innovate_matches_innovate_signal(self):
        sg = _subgoal("invented a new action", kind="innovate")
        assert check_completion(sg, _agent(), _ok(), "innovate")


class TestKindFallback:
    def test_kind_matches_action(self):
        sg = _subgoal("done", kind="rest")
        assert check_completion(sg, _agent(), _ok(), "rest")

    def test_kind_no_match_different_action(self):
        sg = _subgoal("done", kind="eat")
        assert not check_completion(sg, _agent(), _ok(), "move")

    def test_empty_signal_returns_false(self):
        sg = _subgoal("")
        assert not check_completion(sg, _agent(), _ok(), "move")


class TestFailureDetection:
    def test_failure_signal_match(self):
        sg = _subgoal("", "nothing to eat", kind="eat")
        assert check_failure(sg, _agent(), _fail(), "eat", 0)

    def test_no_failure_on_success(self):
        sg = _subgoal("", "nothing to eat")
        assert not check_failure(sg, _agent(), _ok(), "eat", 0)

    def test_consecutive_failures_threshold(self):
        sg = _subgoal("", "irrelevant signal", kind="move")
        assert not check_failure(sg, _agent(), _fail(), "move", 2)
        assert check_failure(sg, _agent(), _fail(), "move", 3)
