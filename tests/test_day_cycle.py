"""
Unit tests for DayCycle.

No LLM required. Tests cover hour calculation, period detection,
vision radius, energy multiplier, and prompt line generation.

Day structure (default start_hour=6):
  - tick 1  → hour 6  (day)
  - tick 11 → hour 16 (sunset)
  - tick 16 → hour 21 (night)
  - tick 19 → hour 0  (day, next day)
"""

import pytest
from simulation.day_cycle import DayCycle


# ──────────────────────────────────────────────────────────────────────────────
# Hour calculation
# ──────────────────────────────────────────────────────────────────────────────

def test_hour_at_tick_1_start_6():
    dc = DayCycle(start_hour=6)
    assert dc.get_hour(1) == 6


def test_hour_at_tick_2_start_6():
    dc = DayCycle(start_hour=6)
    assert dc.get_hour(2) == 7


def test_hour_wraps_at_midnight():
    # tick 19 with start_hour=6 → (18 + 6) % 24 = 0 (midnight)
    dc = DayCycle(start_hour=6)
    assert dc.get_hour(19) == 0


def test_hour_midnight_start():
    dc = DayCycle(start_hour=0)
    assert dc.get_hour(1) == 0
    assert dc.get_hour(24) == 23
    assert dc.get_hour(25) == 0  # wraps


def test_hour_start_21():
    # Start at night hour 21
    dc = DayCycle(start_hour=21)
    assert dc.get_hour(1) == 21
    assert dc.get_hour(4) == 0   # (3 + 21) % 24 = 0


# ──────────────────────────────────────────────────────────────────────────────
# Day number
# ──────────────────────────────────────────────────────────────────────────────

def test_day_1_at_start():
    dc = DayCycle(start_hour=6)
    assert dc.get_day(1) == 1


def test_day_increments_after_24h():
    # With start_hour=6:
    #   tick 18 → hour 23 → still day 1 (18 + 6 - 1 = 23, 23//24 = 0)
    #   tick 19 → hour 0  → day 2 (19 + 6 - 1 = 24, 24//24 = 1, +1 = 2)
    dc = DayCycle(start_hour=6)
    assert dc.get_day(18) == 1
    assert dc.get_day(19) == 2


def test_day_3_at_tick_49():
    # tick 49, start=6: (48 + 6) // 24 + 1 = 54 // 24 + 1 = 2 + 1 = 3
    dc = DayCycle(start_hour=6)
    assert dc.get_day(49) == 3


# ──────────────────────────────────────────────────────────────────────────────
# Period detection
# ──────────────────────────────────────────────────────────────────────────────

def test_period_day():
    dc = DayCycle(start_hour=6)
    # tick 1 → hour 6 → day
    assert dc.get_period(1) == "day"


def test_period_sunset():
    dc = DayCycle(start_hour=6)
    # tick 11 → hour 16 → sunset
    assert dc.get_period(11) == "sunset"


def test_period_night():
    dc = DayCycle(start_hour=6)
    # tick 16 → hour 21 → night
    assert dc.get_period(16) == "night"


def test_period_at_last_night_hour():
    dc = DayCycle(start_hour=6)
    # tick 18 → hour 23 → night
    assert dc.get_period(18) == "night"


def test_period_wraps_to_day():
    dc = DayCycle(start_hour=6)
    # tick 19 → hour 0 → day (hour 0 < 16)
    assert dc.get_period(19) == "day"


def test_period_sunset_boundary():
    # Hour exactly at SUNSET_START_HOUR (16) should be "sunset"
    dc = DayCycle(start_hour=0)
    # tick 17 → hour 16 → sunset
    assert dc.get_period(17) == "sunset"


def test_period_night_boundary():
    # Hour exactly at NIGHT_START_HOUR (21) should be "night"
    dc = DayCycle(start_hour=0)
    # tick 22 → hour 21 → night
    assert dc.get_period(22) == "night"


# ──────────────────────────────────────────────────────────────────────────────
# Vision radius
# ──────────────────────────────────────────────────────────────────────────────

def test_vision_radius_day():
    dc = DayCycle(start_hour=6)
    assert dc.get_vision_radius(1) == 3   # full


def test_vision_radius_sunset():
    dc = DayCycle(start_hour=6)
    assert dc.get_vision_radius(11) == 2  # -1


def test_vision_radius_night():
    dc = DayCycle(start_hour=6)
    assert dc.get_vision_radius(16) == 1  # -2


# ──────────────────────────────────────────────────────────────────────────────
# Energy multiplier
# ──────────────────────────────────────────────────────────────────────────────

def test_energy_multiplier_day():
    dc = DayCycle(start_hour=6)
    assert dc.get_energy_multiplier(1) == 1.0


def test_energy_multiplier_sunset():
    dc = DayCycle(start_hour=6)
    # Sunset has no energy multiplier
    assert dc.get_energy_multiplier(11) == 1.0


def test_energy_multiplier_night():
    dc = DayCycle(start_hour=6)
    assert dc.get_energy_multiplier(16) == 1.5


# ──────────────────────────────────────────────────────────────────────────────
# Prompt line
# ──────────────────────────────────────────────────────────────────────────────

def test_prompt_line_day_contains_full_vision():
    dc = DayCycle(start_hour=6)
    line = dc.get_prompt_line(1)
    assert "Day" in line
    assert "3" in line   # full vision = 3 tiles


def test_prompt_line_sunset_contains_reduced_vision():
    dc = DayCycle(start_hour=6)
    line = dc.get_prompt_line(11)
    assert "Sunset" in line
    assert "2" in line   # vision = 2


def test_prompt_line_night_mentions_1_tile():
    dc = DayCycle(start_hour=6)
    line = dc.get_prompt_line(16)
    assert "Night" in line
    assert "1" in line   # vision = 1


def test_prompt_line_night_warns_energy():
    dc = DayCycle(start_hour=6)
    line = dc.get_prompt_line(16)
    assert "50%" in line or "rest" in line.lower()


def test_prompt_line_shows_hour():
    dc = DayCycle(start_hour=6)
    line = dc.get_prompt_line(1)   # hour 6
    assert "06:00" in line
