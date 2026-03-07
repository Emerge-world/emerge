from unittest.mock import MagicMock, patch

from simulation.agent import Agent
from simulation.config import (
    TEACH_ENERGY_COST_TEACHER, TEACH_ENERGY_COST_LEARNER,
    TEACH_TRUST_DELTA, AGENT_VISION_RADIUS, BASE_ACTIONS,
)
from simulation.oracle import Oracle


def make_teacher_learner():
    teacher = Agent(name="Ada", x=5, y=5)
    teacher.energy = 50
    # Teacher knows an innovation
    teacher.actions.append("fire_making")
    learner = Agent(name="Bruno", x=7, y=5)  # 2 tiles away, within vision radius (3)
    learner.energy = 30
    return teacher, learner


def make_oracle(teacher, learner):
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [teacher, learner]
    # Register the innovation as a precedent
    oracle.precedents["innovation:fire_making"] = {
        "description": "Make fire from stones",
        "effects": {"energy": 10},
    }
    return oracle


# --- Happy path ---

def test_teach_learner_gains_action():
    teacher, learner = make_teacher_learner()
    oracle = make_oracle(teacher, learner)
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "sharing"}
    result = oracle.resolve_action(teacher, action, tick=1)
    assert result["success"] is True
    assert "fire_making" in learner.actions


def test_teach_teacher_loses_energy():
    teacher, learner = make_teacher_learner()
    oracle = make_oracle(teacher, learner)
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    oracle.resolve_action(teacher, action, tick=1)
    assert teacher.energy == 50 - TEACH_ENERGY_COST_TEACHER


def test_teach_learner_loses_energy():
    teacher, learner = make_teacher_learner()
    oracle = make_oracle(teacher, learner)
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    oracle.resolve_action(teacher, action, tick=1)
    assert learner.energy == 30 - TEACH_ENERGY_COST_LEARNER


def test_teach_both_gain_trust():
    teacher, learner = make_teacher_learner()
    oracle = make_oracle(teacher, learner)
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    oracle.resolve_action(teacher, action, tick=1)
    # Teacher trusts learner more
    assert "Bruno" in teacher.relationships
    assert abs(teacher.relationships["Bruno"].trust - TEACH_TRUST_DELTA) < 0.001
    # Learner trusts teacher more
    assert "Ada" in learner.relationships
    assert abs(learner.relationships["Ada"].trust - TEACH_TRUST_DELTA) < 0.001


def test_teach_both_increment_cooperations():
    teacher, learner = make_teacher_learner()
    oracle = make_oracle(teacher, learner)
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    oracle.resolve_action(teacher, action, tick=1)
    assert teacher.relationships["Bruno"].cooperations >= 1
    assert learner.relationships["Ada"].cooperations >= 1


def test_teach_both_get_episodic_memory():
    teacher, learner = make_teacher_learner()
    oracle = make_oracle(teacher, learner)
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    oracle.resolve_action(teacher, action, tick=1)
    teacher_memories = " ".join(teacher.memory)
    learner_memories = " ".join(learner.memory)
    assert "Bruno" in teacher_memories or "fire_making" in teacher_memories
    assert "Ada" in learner_memories or "fire_making" in learner_memories


def test_teach_within_vision_radius_succeeds():
    teacher = Agent(name="Ada", x=0, y=0)
    teacher.energy = 50
    teacher.actions.append("fire_making")
    # Exactly at vision radius
    learner = Agent(name="Bruno", x=AGENT_VISION_RADIUS, y=0)
    learner.energy = 30
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [teacher, learner]
    oracle.precedents["innovation:fire_making"] = {"description": "fire"}
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    result = oracle.resolve_action(teacher, action, tick=1)
    assert result["success"] is True


def test_teach_no_llm_call_made():
    """Teaching must be deterministic - no LLM involved (DEC-024)."""
    teacher, learner = make_teacher_learner()
    oracle = make_oracle(teacher, learner)
    mock_llm = MagicMock()
    oracle.llm = mock_llm
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    oracle.resolve_action(teacher, action, tick=1)
    mock_llm.generate_json.assert_not_called()


# --- Failure cases ---

def test_teach_target_not_found():
    teacher, _ = make_teacher_learner()
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [teacher]
    oracle.precedents["innovation:fire_making"] = {"description": "fire"}
    action = {"action": "teach", "target": "Ghost", "skill": "fire_making", "reason": "test"}
    result = oracle.resolve_action(teacher, action, tick=1)
    assert result["success"] is False


def test_teach_target_dead():
    teacher, learner = make_teacher_learner()
    learner.alive = False
    oracle = make_oracle(teacher, learner)
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    result = oracle.resolve_action(teacher, action, tick=1)
    assert result["success"] is False


def test_teach_target_out_of_range():
    teacher = Agent(name="Ada", x=0, y=0)
    teacher.energy = 50
    teacher.actions.append("fire_making")
    far_learner = Agent(name="Bruno", x=10, y=10)  # far beyond vision radius
    far_learner.energy = 30
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [teacher, far_learner]
    oracle.precedents["innovation:fire_making"] = {"description": "fire"}
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    result = oracle.resolve_action(teacher, action, tick=1)
    assert result["success"] is False


def test_teach_teacher_doesnt_know_skill():
    teacher, learner = make_teacher_learner()
    oracle = make_oracle(teacher, learner)
    action = {"action": "teach", "target": "Bruno", "skill": "unknown_skill", "reason": "test"}
    result = oracle.resolve_action(teacher, action, tick=1)
    assert result["success"] is False


def test_teach_base_action_rejected():
    """Cannot teach a base action (it's already known by all)."""
    teacher, learner = make_teacher_learner()
    oracle = make_oracle(teacher, learner)
    base_skill = BASE_ACTIONS[0]
    action = {"action": "teach", "target": "Bruno", "skill": base_skill, "reason": "test"}
    result = oracle.resolve_action(teacher, action, tick=1)
    assert result["success"] is False


def test_teach_learner_already_knows_skill():
    teacher, learner = make_teacher_learner()
    learner.actions.append("fire_making")
    oracle = make_oracle(teacher, learner)
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    result = oracle.resolve_action(teacher, action, tick=1)
    assert result["success"] is False


def test_teach_teacher_insufficient_energy():
    teacher, learner = make_teacher_learner()
    teacher.energy = TEACH_ENERGY_COST_TEACHER - 1
    oracle = make_oracle(teacher, learner)
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    result = oracle.resolve_action(teacher, action, tick=1)
    assert result["success"] is False


def test_teach_learner_insufficient_energy():
    teacher, learner = make_teacher_learner()
    learner.energy = TEACH_ENERGY_COST_LEARNER - 1
    oracle = make_oracle(teacher, learner)
    action = {"action": "teach", "target": "Bruno", "skill": "fire_making", "reason": "test"}
    result = oracle.resolve_action(teacher, action, tick=1)
    assert result["success"] is False
