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
from simulation.evolution.prompt_config import PromptConfig
from simulation.evolution.prompt_evolver import PromptEvolver
import simulation.prompt_loader as prompt_loader

logger = logging.getLogger(__name__)


class EvolutionRunner:
    """
    Orchestrates the evolution loop: generate variants, run simulations,
    select survivors, and repeat.

    Three independent evolution axes (any can be None/disabled):
      - world schema (WorldEvolver)
      - agent prompts (PromptEvolver with scope="agent")
      - oracle prompts (PromptEvolver with scope="oracle")

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
        "evolve_world": True,
        "evolve_agent_prompts": False,
        "evolve_oracle_prompts": False,
    }

    def __init__(
        self,
        tree: EvolutionTree,
        evolver: WorldEvolver,
        engine_factory,  # callable(schema, seed, ...) -> SimulationEngine
        interactive: bool = False,
        data_dir: Path | str = "data",
        agent_prompt_evolver: Optional[PromptEvolver] = None,
        oracle_prompt_evolver: Optional[PromptEvolver] = None,
    ):
        self.tree = tree
        self.evolver = evolver
        self.engine_factory = engine_factory
        self.interactive = interactive
        self.data_dir = Path(data_dir)
        self.agent_prompt_evolver = agent_prompt_evolver
        self.oracle_prompt_evolver = oracle_prompt_evolver

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
        agent_prompt_evolver: Optional[PromptEvolver] = None,
        oracle_prompt_evolver: Optional[PromptEvolver] = None,
    ) -> "EvolutionRunner":
        """Create a new evolution run from scratch."""
        full_config = {**cls.DEFAULT_CONFIG, **config}
        tree = EvolutionTree.create(base_dir, full_config)

        # Register generation 0 base node
        if base_schema is None:
            base_schema = WorldSchema.load_default()

        schema_path = tree.schema_path_for(0, "variant_base")
        base_schema.save(schema_path)

        # Save baseline prompt configs
        baseline_prompts = PromptConfig.from_disk()
        agent_path = tree.agent_prompts_path_for(0, "variant_base")
        oracle_path = tree.oracle_prompts_path_for(0, "variant_base")
        agent_config = PromptConfig(
            agent_prompts=baseline_prompts.agent_prompts, oracle_prompts={},
        )
        oracle_config = PromptConfig(
            agent_prompts={}, oracle_prompts=baseline_prompts.oracle_prompts,
        )
        agent_config.save(agent_path)
        oracle_config.save(oracle_path)

        tree.add_node(
            node_id="gen0_base",
            generation=0,
            parent=None,
            schema_path=str(schema_path.relative_to(tree.tree_dir)),
            agent_prompts_path=str(agent_path.relative_to(tree.tree_dir)),
            oracle_prompts_path=str(oracle_path.relative_to(tree.tree_dir)),
        )
        tree.save()

        return cls(
            tree, evolver, engine_factory, interactive, data_dir,
            agent_prompt_evolver, oracle_prompt_evolver,
        )

    @classmethod
    def resume(
        cls,
        tree_json_path: Path | str,
        evolver: WorldEvolver,
        engine_factory,
        interactive: bool = False,
        data_dir: Path | str = "data",
        agent_prompt_evolver: Optional[PromptEvolver] = None,
        oracle_prompt_evolver: Optional[PromptEvolver] = None,
    ) -> "EvolutionRunner":
        """Resume an existing evolution run."""
        tree = EvolutionTree.resume(tree_json_path)
        return cls(
            tree, evolver, engine_factory, interactive, data_dir,
            agent_prompt_evolver, oracle_prompt_evolver,
        )

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
        prompt_override = self._build_prompt_override(node)
        run_dirs = []
        for r in range(runs_per_variant):
            run_dir = self._run_single(schema, run_index=r, prompt_override=prompt_override)
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
        config = self.tree.config
        evolve_world = config.get("evolve_world", True)
        evolve_agent = config.get("evolve_agent_prompts", False)
        evolve_oracle = config.get("evolve_oracle_prompts", False)

        schema_path = self.tree.tree_dir / parent.schema_path
        schema = WorldSchema.load(schema_path)

        # Load parent prompt configs (for inheritance)
        parent_agent_cfg = self._load_node_agent_config(parent)
        parent_oracle_cfg = self._load_node_oracle_config(parent)

        # Build run summary from parent's completed runs
        run_dirs = [
            self.data_dir / "runs" / rid
            for rid in parent.runs
            if (self.data_dir / "runs" / rid).exists()
        ]
        run_summary = RunAnalyzer(run_dirs).analyze() if run_dirs else RunSummary()

        # Generate world schema variants (or repeat parent schema)
        if evolve_world and self.evolver is not None:
            world_variants = self.evolver.mutate(schema, run_summary, n=branches)
        else:
            # Freeze world: repeat parent schema for each branch
            world_variants = [schema] * branches

        # Generate agent prompt variants (or repeat parent)
        baseline_for_agent = parent_agent_cfg or PromptConfig.from_disk()
        if evolve_agent and self.agent_prompt_evolver is not None:
            agent_variants = self.agent_prompt_evolver.mutate(
                baseline_for_agent, run_summary, n=branches, scope="agent"
            )
            # Pad with copies if we got fewer than branches
            while len(agent_variants) < branches:
                agent_variants.append(baseline_for_agent)
        else:
            agent_variants = [baseline_for_agent] * branches

        # Generate oracle prompt variants (or repeat parent)
        baseline_for_oracle = parent_oracle_cfg or PromptConfig.from_disk()
        if evolve_oracle and self.oracle_prompt_evolver is not None:
            oracle_variants = self.oracle_prompt_evolver.mutate(
                baseline_for_oracle, run_summary, n=branches, scope="oracle"
            )
            while len(oracle_variants) < branches:
                oracle_variants.append(baseline_for_oracle)
        else:
            oracle_variants = [baseline_for_oracle] * branches

        logger.info(
            "Generated variants from parent %s (gen %d): world=%d agent=%d oracle=%d",
            parent.node_id, generation,
            len(world_variants), len(agent_variants), len(oracle_variants),
        )

        for v_idx, variant_schema in enumerate(world_variants):
            variant_name = f"from_{parent.node_id}_v{v_idx}"
            node_id = f"gen{generation}_{variant_name}"

            # Save world schema
            schema_path_new = self.tree.schema_path_for(generation, variant_name)
            variant_schema.save(schema_path_new)

            # Save mutations metadata
            mutations_path = self.tree.mutations_path_for(generation, variant_name)
            mutations_path.write_text(
                yaml.dump(variant_schema.metadata.get("mutations_applied", []),
                          default_flow_style=False)
            )

            # Save prompt configs for this variant
            av = agent_variants[v_idx] if v_idx < len(agent_variants) else baseline_for_agent
            ov = oracle_variants[v_idx] if v_idx < len(oracle_variants) else baseline_for_oracle

            agent_path = self.tree.agent_prompts_path_for(generation, variant_name)
            oracle_path = self.tree.oracle_prompts_path_for(generation, variant_name)
            # Save only the relevant scope in each file
            PromptConfig(agent_prompts=av.agent_prompts, oracle_prompts={}).save(agent_path)
            PromptConfig(agent_prompts={}, oracle_prompts=ov.oracle_prompts).save(oracle_path)

            # Register in tree
            self.tree.add_node(
                node_id=node_id,
                generation=generation,
                parent=parent.node_id,
                schema_path=str(schema_path_new.relative_to(self.tree.tree_dir)),
                agent_prompts_path=str(agent_path.relative_to(self.tree.tree_dir)),
                oracle_prompts_path=str(oracle_path.relative_to(self.tree.tree_dir)),
            )
            self.tree.save()

            # Build prompt override for this variant's runs
            node = self.tree.nodes[node_id]
            prompt_override = self._build_prompt_override_from_configs(av, ov)

            # Run simulations
            run_dirs_new = []
            for r in range(runs_per_variant):
                run_dir = self._run_single(
                    variant_schema, run_index=r, prompt_override=prompt_override
                )
                if run_dir:
                    self.tree.record_run(node_id, run_dir.name)
                    run_dirs_new.append(run_dir)
                    self.tree.save()

            self._finalize_node(node_id, run_dirs_new)
            self.tree.save()

    def _build_prompt_override(self, node: EvolutionNode) -> Optional[dict[str, str]]:
        """Build prompt override dict from a node's saved prompt configs."""
        agent_cfg = self._load_node_agent_config(node)
        oracle_cfg = self._load_node_oracle_config(node)
        return self._build_prompt_override_from_configs(agent_cfg, oracle_cfg)

    def _build_prompt_override_from_configs(
        self,
        agent_cfg: Optional[PromptConfig],
        oracle_cfg: Optional[PromptConfig],
    ) -> Optional[dict[str, str]]:
        """Merge agent and oracle configs into a flat loader dict, or None if both empty."""
        result: dict[str, str] = {}
        if agent_cfg:
            result.update(agent_cfg.to_loader_dict())
        if oracle_cfg:
            result.update(oracle_cfg.to_loader_dict())
        return result if result else None

    def _load_node_agent_config(self, node: EvolutionNode) -> Optional[PromptConfig]:
        if not node.agent_prompts_path:
            return None
        path = self.tree.tree_dir / node.agent_prompts_path
        if not path.exists():
            return None
        try:
            return PromptConfig.load(path)
        except Exception as exc:
            logger.warning("Failed to load agent prompts for %s: %s", node.node_id, exc)
            return None

    def _load_node_oracle_config(self, node: EvolutionNode) -> Optional[PromptConfig]:
        if not node.oracle_prompts_path:
            return None
        path = self.tree.tree_dir / node.oracle_prompts_path
        if not path.exists():
            return None
        try:
            return PromptConfig.load(path)
        except Exception as exc:
            logger.warning("Failed to load oracle prompts for %s: %s", node.node_id, exc)
            return None

    def _run_single(
        self,
        schema: WorldSchema,
        run_index: int = 0,
        prompt_override: Optional[dict[str, str]] = None,
    ) -> Optional[Path]:
        """Run one simulation with the given schema. Returns run output dir."""
        config = self.tree.config
        ticks = config.get("ticks_per_run", 200)
        agents = config.get("agents_per_run", 10)
        use_llm = config.get("use_llm", False)
        seed = run_index

        try:
            prompt_loader.set_override(prompt_override)
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
        finally:
            prompt_loader.set_override(None)

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
