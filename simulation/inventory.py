"""
Agent inventory: carries items collected from the world.
Capacity is measured by total quantity (not unique item types).
"""


class Inventory:
    """Quantity-based item inventory for an agent."""

    def __init__(self, capacity: int = 10):
        self.items: dict[str, int] = {}
        self.capacity: int = capacity

    def add(self, item: str, qty: int) -> int:
        """Add qty of item. Returns actual qty added (clipped to free space)."""
        if not item or not item.strip():
            return 0
        if qty <= 0:
            return 0
        can_add = min(qty, self.free_space())
        if can_add > 0:
            self.items[item] = self.items.get(item, 0) + can_add
        return can_add

    def remove(self, item: str, qty: int) -> bool:
        """Remove qty of item. Returns True if had enough, False otherwise."""
        if qty <= 0:
            return False
        if not self.has(item, qty):
            return False
        self.items[item] -= qty
        if self.items[item] == 0:
            del self.items[item]
        return True

    def has(self, item: str, qty: int = 1) -> bool:
        """Return True if carrying at least qty of item."""
        return self.items.get(item, 0) >= qty

    def total(self) -> int:
        """Total number of items carried (sum of all quantities)."""
        return sum(self.items.values())

    def free_space(self) -> int:
        """Remaining capacity."""
        return self.capacity - self.total()

    def is_empty(self) -> bool:
        return self.total() == 0

    def to_prompt(self) -> str:
        """Returns inventory line for the decision prompt. Empty string if empty."""
        if self.is_empty():
            return ""
        parts = [f"{item} x{qty}" for item, qty in sorted(self.items.items())]
        return f"INVENTORY: {', '.join(parts)} ({self.total()}/{self.capacity})"

    def to_dict(self) -> dict:
        return {"items": dict(self.items), "capacity": self.capacity}

    @classmethod
    def from_dict(cls, data: dict) -> "Inventory":
        inv = cls(capacity=data.get("capacity", 10))
        inv.items = {
            k: v for k, v in data.get("items", {}).items()
            if isinstance(k, str) and k.strip() and isinstance(v, int) and v > 0
        }
        return inv
