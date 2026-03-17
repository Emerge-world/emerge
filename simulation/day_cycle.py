"""
Day/night cycle: maps simulation ticks to in-world hours and time periods.

1 tick = 1 hour in world time.
Periods:
  - day    (hours  0–15): full vision, normal energy costs
  - sunset (hours 16–20): vision radius −1, normal energy costs
  - night  (hours 21–23): vision radius −2, energy action costs ×1.5

If a WorldSchema is provided to the constructor, all timing parameters are
read from the schema instead of config.py constants.
"""

from typing import TYPE_CHECKING, Optional

from simulation.config import (
    DAY_LENGTH,
    WORLD_START_HOUR,
    SUNSET_START_HOUR,
    NIGHT_START_HOUR,
    NIGHT_VISION_REDUCTION,
    SUNSET_VISION_REDUCTION,
    NIGHT_ENERGY_MULTIPLIER,
    AGENT_VISION_RADIUS,
)

if TYPE_CHECKING:
    from simulation.world_schema import WorldSchema


class DayCycle:
    """Encapsulates all time-of-day logic for the simulation."""

    def __init__(self, start_hour: int = WORLD_START_HOUR, world_schema: Optional["WorldSchema"] = None):
        if world_schema is not None:
            dn = world_schema.day_night
            self.start_hour = dn["start_hour"]
            self._day_length = dn["day_length"]
            self._sunset_start = dn["sunset_start"]
            self._night_start = dn["night_start"]
            self._night_vision_reduction = dn["night_vision_reduction"]
            self._sunset_vision_reduction = dn["sunset_vision_reduction"]
            self._night_energy_multiplier = float(dn["night_energy_multiplier"])
            self._vision_radius = world_schema.agents["vision_radius"]
        else:
            self.start_hour = start_hour
            self._day_length = DAY_LENGTH
            self._sunset_start = SUNSET_START_HOUR
            self._night_start = NIGHT_START_HOUR
            self._night_vision_reduction = NIGHT_VISION_REDUCTION
            self._sunset_vision_reduction = SUNSET_VISION_REDUCTION
            self._night_energy_multiplier = NIGHT_ENERGY_MULTIPLIER
            self._vision_radius = AGENT_VISION_RADIUS

    def get_hour(self, tick: int) -> int:
        """Return the current in-world hour (0–23) for a given tick."""
        return (tick - 1 + self.start_hour) % self._day_length

    def get_day(self, tick: int) -> int:
        """Return the current in-world day number (1-indexed)."""
        return (tick - 1 + self.start_hour) // self._day_length + 1

    def get_period(self, tick: int) -> str:
        """Return the time period: 'day', 'sunset', or 'night'."""
        hour = self.get_hour(tick)
        if hour >= self._night_start:
            return "night"
        if hour >= self._sunset_start:
            return "sunset"
        return "day"

    def get_vision_radius(self, tick: int) -> int:
        """Return the effective agent vision radius for this tick."""
        period = self.get_period(tick)
        if period == "night":
            return self._vision_radius - self._night_vision_reduction
        if period == "sunset":
            return self._vision_radius - self._sunset_vision_reduction
        return self._vision_radius

    def get_energy_multiplier(self, tick: int) -> float:
        """Return the energy cost multiplier for action costs (not recovery)."""
        if self.get_period(tick) == "night":
            return self._night_energy_multiplier
        return 1.0

    def get_prompt_line(self, tick: int) -> str:
        """Return a one-line time description for the agent decision prompt."""
        hour = self.get_hour(tick)
        day = self.get_day(tick)
        period = self.get_period(tick)
        vision = self.get_vision_radius(tick)
        time_str = f"{hour:02d}:00, day {day}"

        if period == "day":
            return f"TIME: Day ({time_str}). Full vision ({vision} tiles). Normal energy costs."
        if period == "sunset":
            return f"TIME: Sunset ({time_str}). Vision reduced to {vision} tiles."
        return (
            f"TIME: Night ({time_str}). Vision severely reduced to {vision} tile. "
            f"Energy costs 50% higher — rest is strongly advisable."
        )
