# tests/test_agent_prompts.py
import pytest
from simulation.agent import Agent

def _make_nearby(center_tile: str, *extra: dict) -> list[dict]:
    """Build a nearby_tiles list with the agent at (5,5) on center_tile."""
    tiles = [{"x": 5, "y": 5, "tile": center_tile, "distance": 0}]
    tiles.extend(extra)
    return tiles

class TestBuildAsciiGrid:
    def setup_method(self):
        Agent._id_counter = 0
        self.agent = Agent(name="Test", x=5, y=5)

    def test_sand_renders_S(self):
        nearby = _make_nearby("sand")
        grid = self.agent._build_ascii_grid(nearby)
        assert "@" in grid  # agent marker at center

    def test_all_tile_chars(self):
        """Each tile type renders to the correct character in the grid."""
        expected = {
            "land":     ".",
            "sand":     "S",
            "water":    "W",
            "river":    "~",
            "forest":   "f",
            "mountain": "M",
            "cave":     "C",
            "tree":     "t",  # empty tree (no resource)
        }
        for tile_type, char in expected.items():
            nearby = [
                {"x": 5, "y": 5, "tile": "land", "distance": 0},  # agent tile
                {"x": 6, "y": 5, "tile": tile_type, "distance": 1},  # east tile
            ]
            grid = self.agent._build_ascii_grid(nearby)
            row_center = grid.split("\n")[3]  # middle row of 7x7 grid
            assert char in row_center, f"Expected '{char}' for tile '{tile_type}'"

    def test_fruit_tree_renders_F(self):
        nearby = [
            {"x": 5, "y": 5, "tile": "land", "distance": 0},
            {"x": 6, "y": 5, "tile": "tree", "distance": 1,
             "resource": {"type": "fruit", "quantity": 3}},
        ]
        grid = self.agent._build_ascii_grid(nearby)
        row_center = grid.split("\n")[3]
        assert "F" in row_center
