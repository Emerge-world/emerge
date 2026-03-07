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
