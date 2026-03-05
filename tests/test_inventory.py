"""Unit tests for the Inventory class."""
import pytest
from simulation.inventory import Inventory


class TestInventoryAdd:
    def test_add_to_empty(self):
        inv = Inventory(capacity=10)
        added = inv.add("fruit", 3)
        assert added == 3
        assert inv.items["fruit"] == 3

    def test_add_clips_to_capacity(self):
        inv = Inventory(capacity=5)
        added = inv.add("fruit", 10)
        assert added == 5
        assert inv.total() == 5

    def test_add_multiple_types(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 3)
        inv.add("stone", 2)
        assert inv.items["fruit"] == 3
        assert inv.items["stone"] == 2
        assert inv.total() == 5

    def test_add_when_full_returns_zero(self):
        inv = Inventory(capacity=3)
        inv.add("fruit", 3)
        added = inv.add("stone", 1)
        assert added == 0
        assert inv.total() == 3

    def test_add_partially_fills(self):
        inv = Inventory(capacity=5)
        inv.add("fruit", 3)
        added = inv.add("stone", 4)  # only 2 slots left
        assert added == 2
        assert inv.total() == 5


class TestInventoryRemove:
    def test_remove_success(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 3)
        result = inv.remove("fruit", 2)
        assert result is True
        assert inv.items["fruit"] == 1

    def test_remove_deletes_key_at_zero(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 2)
        inv.remove("fruit", 2)
        assert "fruit" not in inv.items

    def test_remove_fails_not_enough(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 1)
        result = inv.remove("fruit", 5)
        assert result is False
        assert inv.items["fruit"] == 1  # unchanged

    def test_remove_fails_missing_item(self):
        inv = Inventory(capacity=10)
        result = inv.remove("stone", 1)
        assert result is False


class TestInventoryHas:
    def test_has_enough(self):
        inv = Inventory(capacity=10)
        inv.add("stone", 3)
        assert inv.has("stone", 3) is True
        assert inv.has("stone", 1) is True

    def test_has_not_enough(self):
        inv = Inventory(capacity=10)
        inv.add("stone", 2)
        assert inv.has("stone", 3) is False

    def test_has_missing_item(self):
        inv = Inventory(capacity=10)
        assert inv.has("fruit", 1) is False

    def test_has_default_qty_one(self):
        inv = Inventory(capacity=10)
        inv.add("mushroom", 1)
        assert inv.has("mushroom") is True


class TestInventoryCapacity:
    def test_total_empty(self):
        inv = Inventory(capacity=10)
        assert inv.total() == 0

    def test_total_mixed(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 2)
        inv.add("stone", 3)
        assert inv.total() == 5

    def test_free_space(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 3)
        assert inv.free_space() == 7

    def test_is_empty_true(self):
        assert Inventory(capacity=10).is_empty() is True

    def test_is_empty_false(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 1)
        assert inv.is_empty() is False


class TestInventoryPrompt:
    def test_to_prompt_empty(self):
        inv = Inventory(capacity=10)
        assert inv.to_prompt() == ""

    def test_to_prompt_with_items(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 2)
        inv.add("stone", 1)
        prompt = inv.to_prompt()
        assert "fruit x2" in prompt
        assert "stone x1" in prompt
        assert "3/10" in prompt
        assert prompt.startswith("INVENTORY:")

    def test_to_prompt_sorted_alphabetically(self):
        inv = Inventory(capacity=10)
        inv.add("stone", 1)
        inv.add("fruit", 2)
        prompt = inv.to_prompt()
        assert prompt.index("fruit") < prompt.index("stone")


class TestInventorySerialization:
    def test_to_dict(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 3)
        d = inv.to_dict()
        assert d == {"items": {"fruit": 3}, "capacity": 10}

    def test_from_dict_roundtrip(self):
        inv = Inventory(capacity=15)
        inv.add("fruit", 4)
        inv.add("stone", 2)
        restored = Inventory.from_dict(inv.to_dict())
        assert restored.capacity == 15
        assert restored.items == {"fruit": 4, "stone": 2}
        assert restored.total() == 6

    def test_from_dict_empty(self):
        d = {"items": {}, "capacity": 10}
        inv = Inventory.from_dict(d)
        assert inv.is_empty()
        assert inv.capacity == 10


class TestInventoryInputValidation:
    def test_add_zero_qty(self):
        inv = Inventory(capacity=10)
        added = inv.add("fruit", 0)
        assert added == 0
        assert inv.is_empty()

    def test_add_negative_qty(self):
        inv = Inventory(capacity=10)
        added = inv.add("fruit", -1)
        assert added == 0
        assert inv.is_empty()

    def test_add_empty_item_name(self):
        inv = Inventory(capacity=10)
        added = inv.add("", 3)
        assert added == 0
        assert inv.is_empty()

    def test_add_blank_item_name(self):
        inv = Inventory(capacity=10)
        added = inv.add("  ", 3)
        assert added == 0
        assert inv.is_empty()

    def test_remove_zero_qty(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 3)
        result = inv.remove("fruit", 0)
        assert result is False
        assert inv.items["fruit"] == 3  # unchanged

    def test_remove_negative_qty(self):
        inv = Inventory(capacity=10)
        inv.add("fruit", 3)
        result = inv.remove("fruit", -1)
        assert result is False
        assert inv.items["fruit"] == 3  # unchanged

    def test_from_dict_ignores_invalid_items(self):
        d = {"items": {"fruit": 2, "": 5, "stone": -1, "water": "bad"}, "capacity": 10}
        inv = Inventory.from_dict(d)
        assert inv.has("fruit", 2)
        assert "" not in inv.items
        assert "stone" not in inv.items
        assert "water" not in inv.items
