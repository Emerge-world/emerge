"""
Day/night cycle: maps simulation ticks to in-world hours and time periods.

1 tick = 1 hour in world time.
Periods:
  - day    (hours  0–15): full vision, normal energy costs
  - sunset (hours 16–20): vision radius −1, normal energy costs
  - night  (hours 21–23): vision radius −2, energy action costs ×1.5
"""

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


class DayCycle:
    """Encapsulates all time-of-day logic for the simulation."""

    def __init__(self, start_hour: int = WORLD_START_HOUR):
        self.start_hour = start_hour

    def get_hour(self, tick: int) -> int:
        """Return the current in-world hour (0–23) for a given tick."""
        return (tick - 1 + self.start_hour) % DAY_LENGTH

    def get_day(self, tick: int) -> int:
        """Return the current in-world day number (1-indexed)."""
        return (tick - 1 + self.start_hour) // DAY_LENGTH + 1

    def get_period(self, tick: int) -> str:
        """Return the time period: 'day', 'sunset', or 'night'."""
        hour = self.get_hour(tick)
        if hour >= NIGHT_START_HOUR:
            return "night"
        if hour >= SUNSET_START_HOUR:
            return "sunset"
        return "day"

    def get_vision_radius(self, tick: int) -> int:
        """Return the effective agent vision radius for this tick."""
        period = self.get_period(tick)
        if period == "night":
            return AGENT_VISION_RADIUS - NIGHT_VISION_REDUCTION   # 1
        if period == "sunset":
            return AGENT_VISION_RADIUS - SUNSET_VISION_REDUCTION  # 2
        return AGENT_VISION_RADIUS                                 # 3

    def get_energy_multiplier(self, tick: int) -> float:
        """Return the energy cost multiplier for action costs (not recovery)."""
        if self.get_period(tick) == "night":
            return NIGHT_ENERGY_MULTIPLIER
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
