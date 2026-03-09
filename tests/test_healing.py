"""
Unit tests for passive health regeneration.

No LLM required. Tests cover the healing mechanic added to apply_tick_effects():
agents with hunger < 50 and energy > 30 regenerate +1 life per tick.
"""

import pytest
from simulation.agent import Agent
from simulation.config import (
    AGENT_MAX_LIFE, HEAL_HUNGER_THRESHOLD, HEAL_ENERGY_THRESHOLD, HEAL_PER_TICK,
)


def _make_agent(life=80, hunger=20, energy=50):
    """Create a test agent with specified stats."""
    agent = Agent(name="TestAgent", x=0, y=0)
    agent.life = life
    agent.hunger = hunger
    agent.energy = energy
    return agent


# ──────────────────────────────────────────────────────────────────────────────
# Healing triggers
# ──────────────────────────────────────────────────────────────────────────────

def test_healing_when_well_fed_and_rested():
    agent = _make_agent(life=80, hunger=20, energy=50)
    agent.apply_tick_effects()
    # hunger goes +1 to 21, still below threshold; energy 50 > 30
    assert agent.life == 80 + HEAL_PER_TICK


def test_no_healing_when_hunger_above_threshold():
    agent = _make_agent(life=80, hunger=60, energy=50)
    agent.apply_tick_effects()
    # hunger goes +1 to 61, above threshold of 50
    assert agent.life == 80


def test_no_healing_when_energy_below_threshold():
    agent = _make_agent(life=80, hunger=20, energy=20)
    agent.apply_tick_effects()
    # energy 20 is not > 30
    assert agent.life == 80


def test_no_healing_when_hunger_at_threshold():
    agent = _make_agent(life=80, hunger=49, energy=50)
    agent.apply_tick_effects()
    # hunger goes +1 to 50, NOT < 50
    assert agent.life == 80


def test_no_healing_when_energy_at_threshold():
    agent = _make_agent(life=80, hunger=20, energy=30)
    agent.apply_tick_effects()
    # energy 30 is not > 30
    assert agent.life == 80


# ──────────────────────────────────────────────────────────────────────────────
# Capping and edge cases
# ──────────────────────────────────────────────────────────────────────────────

def test_life_does_not_exceed_max():
    agent = _make_agent(life=AGENT_MAX_LIFE, hunger=20, energy=50)
    agent.apply_tick_effects()
    assert agent.life == AGENT_MAX_LIFE


def test_dead_agents_do_not_heal():
    agent = _make_agent(life=0, hunger=20, energy=50)
    agent.alive = False
    agent.apply_tick_effects()
    assert agent.life == 0
    assert not agent.alive


# ──────────────────────────────────────────────────────────────────────────────
# Interaction with damage mechanics
# ──────────────────────────────────────────────────────────────────────────────

def test_no_healing_during_hunger_damage():
    """Hunger >= 80 and hunger < 50 are mutually exclusive, so healing
    never occurs in the same tick as hunger damage."""
    agent = _make_agent(life=80, hunger=85, energy=50)
    agent.apply_tick_effects()
    # hunger 85 + 1 = 86 >= 80 → life -3, and 86 >= 50 so no healing
    assert agent.life == 80 - 3


def test_no_healing_during_exhaustion_damage():
    """Energy <= 0 and energy > 30 are mutually exclusive."""
    agent = _make_agent(life=80, hunger=20, energy=0)
    agent.apply_tick_effects()
    # energy 0 → life -2, and 0 not > 30 so no healing
    assert agent.life == 80 - 2
