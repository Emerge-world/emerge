"""
EvolutionRunner: orchestrates branching evolution across generations.

Algorithm:
    for gen in 1..max_generations:
        parents = tree.select_top_k(gen-1, k=selection_top_k)
        for parent in parents:
            variants = evolver.mutate(parent.schema, parent.run_data, N=branches_per_gen)
            for variant in variants:
                results = run_batch(variant.schema, M=runs_per_variant)
                tree.record(variant, results)
        if interactive: pause_for_review()
        tree.save()
"""

from __future__ import annotations

import logging
import math
import uuid
from pathlib import Path
from typing import Optional

import yaml

from simulation.world_schema import WorldSchema
from simulation.evolution.evolution_tree import EvolutionTree, EvolutionNode
from simulation.evolution.run_analyzer import RunAnalyzer, RunSummary
from simulation.evolution.world_evolver import WorldEvolver, MockEvolver

logger = logging.getLogger(__name__)


class EvolutionRunner:
    """
    Orchestrates the evolution loop: generate variants, run simulations,
    select survivors, and repeat.

    Usage:
        runner = EvolutionRunner(config, evolver, engine_factory)
        runner.run()

        # Or resume:
        runner = EvolutionRunner.resume(tree_json_path, evolver, engine_factory)
        runner.run()
    """

    DEFAULT_CONFIG = {
        "branches_per_gen": 3,
        "runs_per_variant": 3,
        "max_generations": 10,
        "selection_top_k": 2,
        "ticks_per_run": 200,
        "agents_per_run": 10,
        "use_llm": True,
    }

    def __init__(
        self,
        tree: EvolutionTree,
        evolver: WorldEvolver,
        engine_factory,  # callable(schema, seed, ...) -> SimulationEngine
        interactive: bool = False,
        data_dir: Path | str = "data",
    ):
        self.tree = tree
        self.evolver = evolver
        self.engine_factory = engine_factory
        self.interactive = interactive
        self.data_dir = Path(data_dir)

    @classmethod
    def create(
        cls,
        config: dict,
        evolver: WorldEvolver,
        engine_factory,
        base_schema: Optional[WorldSchema] = None,
        base_dir: Path | str = "data/evolution",
        interactive: bool = False,
        data_dir: Path | str = "data",
    ) -> "EvolutionRunner":
        """Create a new evolution run from scratch."""
        full_config = {**cls.DEFAULT_CONFIG, **config}
        tree = EvolutionTree.create(base_dir, full_config)

        # Register generation 0 base node
        if base_schema is None:
            base_schema = WorldSchema.load_default()

        schema_path = tree.schema_path_for(0, "variant_base")
        base_schema.save(schema_path)
        tree.add_node(
            node_id="gen0_base",
            generation=0,
            parent=None,
            schema_path=str(schema_path.relative_to(tree.tree_dir)),
        )
        tree.save()

        return cls(tree, evolver, engine_factory, interactive, data_dir)

    @classmethod
    def resume(
        cls,
        tree_json_path: Path | str,
        evolver: WorldEvolver,
        engine_factory,
        interactive: bool = False,
        data_dir: Path | str = "data",
    ) -> "EvolutionRunner":
        """Resume an existing evolution run."""
        tree = EvolutionTree.resume(tree_json_path)
        return cls(tree, evolver, engine_factory, interactive, data_dir)

    def run(self) -> None:
        """Execute the evolution loop."""
        config = self.tree.config
        max_gen = config.get("max_generations", 10)
        branches = config.get("branches_per_gen", 3)
        runs_per_variant = config.get("runs_per_variant", 3)
        top_k = config.get("selection_top_k", 2)

        # Always run gen-0 baseline first if not yet done
        if not self.tree.is_generation_complete(0):
            logger.info("Running generation 0 baseline...")
            print("[Evolution] Running gen-0 baseline...")
            self._run_generation_zero(runs_per_variant)
            self.tree.save()

        # Find starting generation (resumability: skip complete generations)
        start_gen = 1
        for g in range(1, max_gen + 1):
            if self.tree.is_generation_complete(g):
                logger.info("Generation %d already complete — skipping", g)
                start_gen = g + 1
            else:
                break

        for gen in range(start_gen, max_gen + 1):
            logger.info("=== Evolution generation %d / %d ===", gen, max_gen)
            print(f"\n[Evolution] Generation {gen}/{max_gen}")

            parents = self.tree.select_top_k(gen - 1, k=top_k)
            if not parents:
                logger.error("Cannot proceed: no parent nodes available for gen %d", gen)
                return

            for parent in parents:
                self._process_parent(parent, branches, runs_per_variant, gen)

            # Mark top-k survivors
            top = self.tree.select_top_k(gen, k=top_k)
            self.tree.mark_selected([n.node_id for n in top])
            self.tree.save()

            if self.interactive:
                self._interactive_pause(gen, top)

        logger.info("Evolution complete after %d generations", max_gen)
        print(f"\n[Evolution] Complete. Tree saved to: {self.tree.tree_dir}/tree.json")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_generation_zero(self, runs_per_variant: int) -> None:
        """Run the baseline gen-0 schema and record results."""
        node = self.tree.nodes.get("gen0_base")
        if node is None:
            return
        schema_path = self.tree.tree_dir / node.schema_path
        schema = WorldSchema.load(schema_path)
        run_dirs = []
        for r in range(runs_per_variant):
            run_dir = self._run_single(schema, run_index=r)
            if run_dir:
                run_id = run_dir.name
                self.tree.record_run("gen0_base", run_id)
                run_dirs.append(run_dir)
        self._finalize_node("gen0_base", run_dirs)
        self.tree.save()

    def _process_parent(
        self,
        parent: EvolutionNode,
        branches: int,
        runs_per_variant: int,
        generation: int,
    ) -> None:
        """Generate variants from a parent and run them."""
        schema_path = self.tree.tree_dir / parent.schema_path
        schema = WorldSchema.load(schema_path)

        # Build run summary from parent's completed runs
        run_dirs = [self.data_dir / "runs" / rid for rid in parent.runs if (self.data_dir / "runs" / rid).exists()]
        run_summary = RunAnalyzer(run_dirs).analyze() if run_dirs else RunSummary()

        # Generate variants
        variants = self.evolver.mutate(schema, run_summary, n=branches)
        logger.info(
            "Generated %d variants from parent %s (gen %d)",
            len(variants), parent.node_id, generation,
        )

        for v_idx, variant in enumerate(variants):
            variant_name = f"from_{parent.node_id}_v{v_idx}"
            node_id = f"gen{generation}_{variant_name}"

            # Save schema
            schema_path_new = self.tree.schema_path_for(generation, variant_name)
            variant.save(schema_path_new)

            # Save mutations metadata
            mutations_path = self.tree.mutations_path_for(generation, variant_name)
            mutations_path.write_text(
                yaml.dump(variant.metadata.get("mutations_applied", []),
                          default_flow_style=False)
            )

            # Register in tree
            self.tree.add_node(
                node_id=node_id,
                generation=generation,
                parent=parent.node_id,
                schema_path=str(schema_path_new.relative_to(self.tree.tree_dir)),
            )
            self.tree.save()

            # Run simulations
            run_dirs_new = []
            for r in range(runs_per_variant):
                run_dir = self._run_single(variant, run_index=r)
                if run_dir:
                    self.tree.record_run(node_id, run_dir.name)
                    run_dirs_new.append(run_dir)
                    self.tree.save()

            self._finalize_node(node_id, run_dirs_new)
            self.tree.save()

    def _run_single(self, schema: WorldSchema, run_index: int = 0) -> Optional[Path]:
        """Run one simulation with the given schema. Returns run output dir."""
        config = self.tree.config
        ticks = config.get("ticks_per_run", 200)
        agents = config.get("agents_per_run", 10)
        use_llm = config.get("use_llm", False)
        seed = run_index  # deterministic across variants; varied across runs of same variant

        try:
            engine = self.engine_factory(
                schema=schema,
                num_agents=agents,
                world_seed=seed,
                use_llm=use_llm,
                max_ticks=ticks,
                run_digest=False,
            )
            engine.run()
            return Path(engine.event_emitter.run_dir)
        except Exception as exc:
            logger.error("Simulation failed (schema=%s, seed=%d): %s",
                         schema.metadata.get("name"), seed, exc)
            return None

    def _finalize_node(self, node_id: str, run_dirs: list[Path]) -> None:
        """Compute and record EBS statistics for a completed node."""
        if not run_dirs:
            return
        summary = RunAnalyzer(run_dirs).analyze()
        self.tree.record_ebs(node_id, summary.mean_ebs, summary.std_ebs)
        logger.info(
            "Node %s finalized: mean_ebs=%.1f std=%.1f (%d runs)",
            node_id, summary.mean_ebs, summary.std_ebs, len(run_dirs),
        )

    def _interactive_pause(self, gen: int, top: list[EvolutionNode]) -> None:
        """Pause for human review between generations."""
        print(f"\n[Evolution] Generation {gen} complete.")
        print(f"  Top survivors:")
        for node in top:
            print(f"    {node.node_id}: mean_ebs={node.mean_ebs:.1f} std={node.std_ebs:.1f}")
        print(f"  Tree: {self.tree.tree_dir}/tree.json")
        input("\nPress Enter to continue to next generation (Ctrl+C to stop)...")


def make_engine_factory(data_dir: str = "data"):
    """
    Create a default engine factory function for use with EvolutionRunner.

    Returns a callable(schema, num_agents, world_seed, use_llm, max_ticks, run_digest)
    that creates a SimulationEngine with the appropriate run_dir rooted in data_dir.
    """
    from simulation.engine import SimulationEngine

    def factory(
        schema: WorldSchema,
        num_agents: int = 10,
        world_seed: Optional[int] = None,
        use_llm: bool = False,
        max_ticks: Optional[int] = 200,
        run_digest: bool = False,
    ) -> SimulationEngine:
        return SimulationEngine(
            num_agents=num_agents,
            world_seed=world_seed,
            use_llm=use_llm,
            max_ticks=max_ticks,
            world_schema=schema,
            run_digest=run_digest,
        )

    return factory
