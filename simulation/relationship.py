from dataclasses import dataclass

from simulation.config import BONDING_TRUST_THRESHOLD, BONDING_COOPERATION_MINIMUM


@dataclass
class Relationship:
    target: str
    trust: float = 0.0
    cooperations: int = 0
    conflicts: int = 0
    last_tick: int = 0
    bonded: bool = False

    @property
    def status(self) -> str:
        if self.trust > 0.6:
            return "friendly"
        if self.trust > 0.2:
            return "neutral"
        if self.trust > -0.3:
            return "wary"
        return "hostile"

    def update(self, delta: float, tick: int, is_cooperation: bool = False, is_conflict: bool = False):
        self.trust = max(-1.0, min(1.0, self.trust + delta))
        self.last_tick = tick
        if is_cooperation:
            self.cooperations += 1
        if is_conflict:
            self.conflicts += 1
        if self.trust >= BONDING_TRUST_THRESHOLD and self.cooperations >= BONDING_COOPERATION_MINIMUM:
            self.bonded = True
