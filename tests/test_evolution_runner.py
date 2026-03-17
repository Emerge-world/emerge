"""
Tests for EvolutionRunner: 2-generation integration test with MockEvolver.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from simulation.world_schema import WorldSchema
from simulation.evolution.evolution_tree import EvolutionTree
from simulation.evolution.evolution_runner import EvolutionRunner, make_engine_factory
from simulation.evolution.world_evolver import MockEvolver


def _make_mock_engine_factory(data_dir: Path):
    """Engine factory that runs a 2-tick simulation and records a run dir."""

    def factory(schema, num_agents=3, world_seed=None, use_llm=False, max_ticks=5, run_digest=False):
        from simulation.engine import SimulationEngine
        return SimulationEngine(
            num_agents=num_agents,
            world_seed=world_seed,
            use_llm=False,
            max_ticks=max_ticks,
            world_schema=schema,
            run_digest=False,
        )

    return factory


@pytest.fixture
def evolution_config() -> dict:
    return {
        "branches_per_gen": 2,
        "runs_per_variant": 1,
        "max_generations": 2,
        "selection_top_k": 1,
        "ticks_per_run": 3,
        "agents_per_run": 1,
        "use_llm": False,
    }


@pytest.fixture
def runner(tmp_path, evolution_config):
    evolver = MockEvolver()
    factory = _make_mock_engine_factory(tmp_path / "data")
    runner = EvolutionRunner.create(
        config=evolution_config,
        evolver=evolver,
        engine_factory=factory,
        base_dir=tmp_path / "evolution",
        data_dir=str(tmp_path / "data"),
    )
    return runner


class TestEvolutionRunnerCreate:
    def test_create_registers_gen0(self, runner):
        assert "gen0_base" in runner.tree.nodes

    def test_create_saves_base_schema(self, runner):
        node = runner.tree.nodes["gen0_base"]
        schema_path = runner.tree.tree_dir / node.schema_path
        assert schema_path.exists()

    def test_create_tree_json_exists(self, runner):
        assert (runner.tree.tree_dir / "tree.json").exists()


class TestEvolutionRunnerResume:
    def test_resume_loads_same_tree(self, runner):
        tree_json = runner.tree.tree_dir / "tree.json"
        resumed = EvolutionRunner.resume(
            tree_json_path=tree_json,
            evolver=MockEvolver(),
            engine_factory=_make_mock_engine_factory(Path("data")),
        )
        assert resumed.tree.tree_id == runner.tree.tree_id
        assert "gen0_base" in resumed.tree.nodes


class TestEvolutionRunnerIntegration:
    def test_two_generation_run(self, runner):
        """Run 2 generations with MockEvolver and verify tree structure."""
        runner.run()
        tree = runner.tree

        # Generation 0 should have been run
        gen0_nodes = tree.get_nodes_by_generation(0)
        assert len(gen0_nodes) == 1
        assert len(gen0_nodes[0].runs) >= 1

        # Generation 1 should have branches_per_gen * top_k nodes
        gen1_nodes = tree.get_nodes_by_generation(1)
        assert len(gen1_nodes) > 0

        # Generation 2 should exist
        gen2_nodes = tree.get_nodes_by_generation(2)
        assert len(gen2_nodes) > 0

    def test_tree_json_updated_after_run(self, runner):
        runner.run()
        data = json.loads((runner.tree.tree_dir / "tree.json").read_text())
        # Should have more than just gen0_base
        assert len(data["nodes"]) > 1

    def test_schema_files_created(self, runner):
        runner.run()
        # Gen 1 variants should have schema files
        gen1_nodes = runner.tree.get_nodes_by_generation(1)
        for node in gen1_nodes:
            schema_path = runner.tree.tree_dir / node.schema_path
            assert schema_path.exists(), f"Schema missing: {schema_path}"

    def test_ebs_recorded_for_all_nodes(self, runner):
        runner.run()
        # All nodes with runs should have EBS recorded (may be 0.0 for short runs)
        for node in runner.tree.nodes.values():
            if node.runs:
                assert isinstance(node.mean_ebs, float)

    def test_top_k_marked_selected(self, runner):
        runner.run()
        # Last gen: top-k should be selected
        max_gen = runner.tree.max_generation()
        top = runner.tree.select_top_k(max_gen, k=runner.tree.config["selection_top_k"])
        selected = [n for n in runner.tree.nodes.values() if n.selected]
        # At least one node should be marked selected
        assert len(selected) > 0

    def test_resume_skips_complete_generations(self, runner, tmp_path):
        """If gen 1 is complete, resume should start from gen 2."""
        # Run fully
        runner.run()

        tree_json = runner.tree.tree_dir / "tree.json"
        new_runner = EvolutionRunner.resume(
            tree_json_path=tree_json,
            evolver=MockEvolver(),
            engine_factory=_make_mock_engine_factory(tmp_path / "data2"),
            data_dir=str(tmp_path / "data2"),
        )
        # Count nodes before re-running
        nodes_before = len(new_runner.tree.nodes)
        # Since all generations are complete, running again should not add duplicate nodes
        new_runner.run()
        nodes_after = len(new_runner.tree.nodes)
        # No new nodes should be added (all gens complete)
        assert nodes_after == nodes_before


class TestMakeEngineFactory:
    def test_factory_creates_engine(self, tmp_path):
        factory = make_engine_factory(data_dir=str(tmp_path))
        schema = WorldSchema.load_default()
        engine = factory(schema=schema, num_agents=1, world_seed=42, use_llm=False, max_ticks=2)
        assert engine is not None

    def test_factory_runs_engine(self, tmp_path):
        factory = make_engine_factory(data_dir=str(tmp_path))
        schema = WorldSchema.load_default()
        engine = factory(schema=schema, num_agents=1, world_seed=42, use_llm=False, max_ticks=2)
        engine.run()  # Should not raise
        assert engine.current_tick == 2
