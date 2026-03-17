"""
Tests for EvolutionTree: node management, selection, persistence.
"""

import json
import pytest
from pathlib import Path

from simulation.evolution.evolution_tree import EvolutionTree, EvolutionNode


@pytest.fixture
def basic_config() -> dict:
    return {
        "branches_per_gen": 2,
        "runs_per_variant": 2,
        "max_generations": 5,
        "selection_top_k": 1,
    }


@pytest.fixture
def tree(tmp_path, basic_config) -> EvolutionTree:
    t = EvolutionTree(tmp_path / "evo_test", basic_config)
    return t


class TestEvolutionTreeCreate:
    def test_create_new_tree(self, tmp_path, basic_config):
        tree = EvolutionTree.create(tmp_path, basic_config)
        assert tree.tree_id.startswith("evo_")
        assert tree.config == basic_config

    def test_tree_dir_created_on_save(self, tree):
        tree.save()
        assert (tree.tree_dir / "tree.json").exists()

    def test_tree_json_structure(self, tree):
        tree.save()
        data = json.loads((tree.tree_dir / "tree.json").read_text())
        assert "tree_id" in data
        assert "config" in data
        assert "nodes" in data


class TestEvolutionNodeManagement:
    def test_add_node(self, tree):
        node = tree.add_node("gen0_base", 0, None, "gen_0/variant_base/world_schema.yaml")
        assert node.node_id == "gen0_base"
        assert node.generation == 0
        assert node.parent is None
        assert "gen0_base" in tree.nodes

    def test_record_run(self, tree):
        tree.add_node("gen0_base", 0, None, "schema.yaml")
        tree.record_run("gen0_base", "run-abc")
        tree.record_run("gen0_base", "run-xyz")
        assert tree.nodes["gen0_base"].runs == ["run-abc", "run-xyz"]

    def test_record_ebs(self, tree):
        tree.add_node("gen1_v0", 1, "gen0_base", "schema.yaml")
        tree.record_ebs("gen1_v0", 55.0, 3.2)
        assert tree.nodes["gen1_v0"].mean_ebs == pytest.approx(55.0)
        assert tree.nodes["gen1_v0"].std_ebs == pytest.approx(3.2)

    def test_mark_selected(self, tree):
        tree.add_node("gen1_v0", 1, None, "a.yaml")
        tree.add_node("gen1_v1", 1, None, "b.yaml")
        tree.mark_selected(["gen1_v0"])
        assert tree.nodes["gen1_v0"].selected is True
        assert tree.nodes["gen1_v1"].selected is False


class TestEvolutionTreePersistence:
    def test_save_and_load(self, tree):
        tree.add_node("gen0_base", 0, None, "schema.yaml")
        tree.record_run("gen0_base", "run-1")
        tree.record_ebs("gen0_base", 42.0, 5.0)
        tree.save()

        tree2 = EvolutionTree(tree.tree_dir, {})
        tree2.load()
        assert "gen0_base" in tree2.nodes
        assert tree2.nodes["gen0_base"].mean_ebs == pytest.approx(42.0)
        assert tree2.nodes["gen0_base"].runs == ["run-1"]

    def test_resume(self, tmp_path, basic_config):
        tree = EvolutionTree.create(tmp_path, basic_config)
        tree.add_node("gen0_base", 0, None, "schema.yaml")
        tree.record_ebs("gen0_base", 30.0, 2.0)
        tree.save()

        tree_json = tree.tree_dir / "tree.json"
        resumed = EvolutionTree.resume(tree_json)
        assert resumed.tree_id == tree.tree_id
        assert "gen0_base" in resumed.nodes

    def test_load_missing_file(self, tmp_path, basic_config):
        tree = EvolutionTree(tmp_path / "nonexistent", basic_config)
        tree.load()  # Should not raise
        assert tree.nodes == {}

    def test_save_overwrites(self, tree):
        tree.add_node("gen0_base", 0, None, "schema.yaml")
        tree.save()
        tree.record_ebs("gen0_base", 99.0, 0.0)
        tree.save()

        tree2 = EvolutionTree(tree.tree_dir, {})
        tree2.load()
        assert tree2.nodes["gen0_base"].mean_ebs == pytest.approx(99.0)


class TestEvolutionTreeSelection:
    def _add_scored_node(self, tree, node_id, gen, mean_ebs, std_ebs, parent=None):
        tree.add_node(node_id, gen, parent, f"{node_id}.yaml")
        tree.record_ebs(node_id, mean_ebs, std_ebs)

    def test_select_top_k_basic(self, tree):
        self._add_scored_node(tree, "g1_v0", 1, 30.0, 2.0)
        self._add_scored_node(tree, "g1_v1", 1, 60.0, 1.0)
        self._add_scored_node(tree, "g1_v2", 1, 50.0, 3.0)
        top = tree.select_top_k(1, k=2)
        assert len(top) == 2
        assert top[0].node_id == "g1_v1"  # highest EBS
        assert top[1].node_id == "g1_v2"  # second

    def test_select_tiebreak_by_std(self, tree):
        self._add_scored_node(tree, "g1_v0", 1, 50.0, 5.0)
        self._add_scored_node(tree, "g1_v1", 1, 50.0, 2.0)  # same EBS, lower std
        top = tree.select_top_k(1, k=1)
        assert top[0].node_id == "g1_v1"

    def test_select_k_larger_than_nodes(self, tree):
        self._add_scored_node(tree, "g1_v0", 1, 40.0, 0.0)
        top = tree.select_top_k(1, k=5)
        assert len(top) == 1

    def test_select_empty_generation(self, tree):
        top = tree.select_top_k(99, k=2)
        assert top == []


class TestEvolutionTreeHelpers:
    def test_get_nodes_by_generation(self, tree):
        tree.add_node("g0_base", 0, None, "a.yaml")
        tree.add_node("g1_v0", 1, "g0_base", "b.yaml")
        tree.add_node("g1_v1", 1, "g0_base", "c.yaml")
        gen1 = tree.get_nodes_by_generation(1)
        assert len(gen1) == 2
        assert all(n.generation == 1 for n in gen1)

    def test_max_generation_empty(self, tree):
        assert tree.max_generation() == -1

    def test_max_generation(self, tree):
        tree.add_node("g0", 0, None, "a.yaml")
        tree.add_node("g2", 2, "g0", "b.yaml")
        assert tree.max_generation() == 2

    def test_is_generation_complete(self, tree):
        tree.add_node("g1_v0", 1, None, "a.yaml")
        tree.add_node("g1_v1", 1, None, "b.yaml")
        assert not tree.is_generation_complete(1)
        # Add runs to both
        for r in range(tree.config["runs_per_variant"]):
            tree.record_run("g1_v0", f"run-a-{r}")
            tree.record_run("g1_v1", f"run-b-{r}")
        assert tree.is_generation_complete(1)

    def test_schema_path_for(self, tree):
        path = tree.schema_path_for(1, "variant_0")
        assert path == tree.tree_dir / "gen_1" / "variant_0" / "world_schema.yaml"

    def test_node_to_dict_roundtrip(self):
        node = EvolutionNode(
            node_id="test", generation=1, parent="gen0",
            schema_path="path.yaml", runs=["r1"], mean_ebs=42.0, std_ebs=1.5, selected=True,
        )
        d = node.to_dict()
        node2 = EvolutionNode.from_dict(d)
        assert node2.node_id == "test"
        assert node2.mean_ebs == pytest.approx(42.0)
        assert node2.selected is True
