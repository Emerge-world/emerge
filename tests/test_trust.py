import pytest

from simulation.relationship import Relationship
from simulation.config import BONDING_TRUST_THRESHOLD, BONDING_COOPERATION_MINIMUM


def test_relationship_defaults():
    rel = Relationship(target="Bruno")
    assert rel.trust == 0.0
    assert rel.cooperations == 0
    assert rel.conflicts == 0
    assert rel.bonded is False


def test_relationship_status_friendly():
    rel = Relationship(target="Bruno", trust=0.7)
    assert rel.status == "friendly"


def test_relationship_status_neutral():
    rel = Relationship(target="Bruno", trust=0.4)
    assert rel.status == "neutral"


def test_relationship_status_wary():
    rel = Relationship(target="Bruno", trust=-0.2)
    assert rel.status == "wary"


def test_relationship_status_hostile():
    rel = Relationship(target="Bruno", trust=-0.5)
    assert rel.status == "hostile"


def test_update_trust_clamped_high():
    rel = Relationship(target="Bruno", trust=0.98)
    rel.update(delta=0.1, tick=5)
    assert rel.trust == 1.0


def test_update_trust_clamped_low():
    rel = Relationship(target="Bruno", trust=-0.98)
    rel.update(delta=-0.1, tick=5)
    assert rel.trust == -1.0


def test_update_cooperation_counter():
    rel = Relationship(target="Bruno")
    rel.update(delta=0.1, tick=5, is_cooperation=True)
    assert rel.cooperations == 1


def test_bonding_trigger():
    rel = Relationship(target="Bruno", trust=0.74, cooperations=2)
    rel.update(delta=0.02, tick=5, is_cooperation=True)
    # trust=0.76, cooperations=3 → bonded
    assert rel.bonded is True


def test_bonding_not_triggered_low_trust():
    rel = Relationship(target="Bruno", trust=0.5, cooperations=4)
    rel.update(delta=0.05, tick=5, is_cooperation=True)
    assert rel.bonded is False  # trust still below threshold


# --- Agent relationship tests ---

from simulation.agent import Agent


def test_agent_has_empty_relationships():
    agent = Agent(name="Kai", x=0, y=0)
    assert agent.relationships == {}


def test_update_relationship_creates_entry():
    agent = Agent(name="Kai", x=0, y=0)
    agent.update_relationship("Bruno", delta=0.1, tick=5, is_cooperation=True)
    assert "Bruno" in agent.relationships
    assert agent.relationships["Bruno"].trust == pytest.approx(0.1, abs=0.001)
    assert agent.relationships["Bruno"].cooperations == 1


def test_get_relationships_prompt_empty():
    agent = Agent(name="Kai", x=0, y=0)
    assert agent.get_relationships_prompt(current_tick=1) == ""


def test_get_relationships_prompt_shows_status():
    agent = Agent(name="Kai", x=0, y=0)
    agent.update_relationship("Bruno", delta=0.7, tick=3, is_cooperation=True)
    prompt = agent.get_relationships_prompt(current_tick=5)
    assert "RELATIONSHIPS:" in prompt
    assert "Bruno" in prompt
    assert "friendly" in prompt.lower()


# --- Oracle trust tests ---

from unittest.mock import MagicMock
from simulation.oracle import Oracle


def test_communicate_builds_trust():
    sender = Agent(name="Kai", x=5, y=5)
    sender.energy = 20
    target = Agent(name="Bruno", x=6, y=5)
    oracle = Oracle(world=MagicMock(), llm=None)
    oracle.current_tick_agents = [sender, target]
    oracle._communicated_this_tick = set()
    action = {"action": "communicate", "target": "Bruno", "message": "Hi!", "intent": "share_info"}
    result = oracle.resolve_action(sender, action, tick=1)
    assert result["success"] is True
    assert "Bruno" in sender.relationships
    assert sender.relationships["Bruno"].trust == pytest.approx(0.05, abs=0.001)
