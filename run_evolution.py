#!/usr/bin/env python3
"""
Evolution runner CLI for Emerge.

Runs the meta-evolution loop: generates world variants via LLM mutation,
runs simulations, and selects the best-performing worlds across generations.

Usage:
    # Fully autonomous (no LLM for simulations, LLM for mutation proposals)
    uv run run_evolution.py --generations 10 --branches 3 --runs 3 --ticks 200

    # No LLM at all (use MockEvolver — for testing/debugging)
    uv run run_evolution.py --generations 2 --branches 2 --runs 1 --ticks 10 --no-llm

    # Human-in-the-loop
    uv run run_evolution.py --generations 10 --branches 3 --runs 3 --interactive

    # Resume from a previous run
    uv run run_evolution.py --resume data/evolution/evo_2026-03-18_01/tree.json

    # Custom base schema
    uv run run_evolution.py --schema data/schemas/base_world.yaml --generations 5
"""

import argparse
import logging
import sys
from pathlib import Path

from simulation.world_schema import WorldSchema
from simulation.evolution.world_evolver import WorldEvolver, MockEvolver
from simulation.evolution.evolution_runner import EvolutionRunner, make_engine_factory


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="World evolution runner for Emerge",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--generations", type=int, default=5,
                   help="Number of evolution generations")
    p.add_argument("--branches", type=int, default=3,
                   help="Number of world variants per parent per generation")
    p.add_argument("--runs", type=int, default=3,
                   help="Number of simulation runs per variant (for statistical significance)")
    p.add_argument("--ticks", type=int, default=200,
                   help="Number of simulation ticks per run")
    p.add_argument("--agents", type=int, default=10,
                   help="Number of agents per simulation run")
    p.add_argument("--top-k", type=int, default=2,
                   help="Number of top-performing variants that survive to next generation")

    p.add_argument("--no-llm", action="store_true",
                   help="Run simulations without LLM (rule-based fallback) and use MockEvolver")
    p.add_argument("--evolver-model", default=None,
                   help="Model override for the world evolver LLM calls (can be different from agent model)")

    p.add_argument("--interactive", action="store_true",
                   help="Pause for human review between generations")

    p.add_argument("--schema", default=None,
                   help="Path to a base WorldSchema YAML (default: data/schemas/base_world.yaml)")
    p.add_argument("--resume", default=None,
                   help="Resume from an existing tree.json file")
    p.add_argument("--evolution-dir", default="data/evolution",
                   help="Base directory for evolution tree storage")
    p.add_argument("--data-dir", default="data",
                   help="Base data directory (where data/runs/ lives)")

    p.add_argument("--verbose", "-v", action="store_true",
                   help="Verbose logging")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    # Build evolver
    if args.no_llm:
        evolver = MockEvolver()
        logger_msg = "MockEvolver (--no-llm)"
    else:
        try:
            from simulation.llm_client import LLMClient
            llm = LLMClient()
            if not llm.is_available():
                print("WARNING: LLM not available — using MockEvolver for world mutations", file=sys.stderr)
                evolver = MockEvolver()
            else:
                evolver = WorldEvolver(llm, model=args.evolver_model)
                logger_msg = f"WorldEvolver (model={llm.model})"
        except Exception as exc:
            print(f"WARNING: Failed to initialize LLM ({exc}) — using MockEvolver", file=sys.stderr)
            evolver = MockEvolver()
            logger_msg = "MockEvolver (LLM init failed)"

    engine_factory = make_engine_factory(data_dir=args.data_dir)

    evolution_config = {
        "branches_per_gen": args.branches,
        "runs_per_variant": args.runs,
        "max_generations": args.generations,
        "selection_top_k": args.top_k,
        "ticks_per_run": args.ticks,
        "agents_per_run": args.agents,
        "use_llm": not args.no_llm,
    }

    if args.resume:
        print(f"Resuming evolution from: {args.resume}")
        runner = EvolutionRunner.resume(
            tree_json_path=args.resume,
            evolver=evolver,
            engine_factory=engine_factory,
            interactive=args.interactive,
            data_dir=args.data_dir,
        )
    else:
        # Load base schema
        base_schema = None
        if args.schema:
            base_schema = WorldSchema.load(args.schema)
            print(f"Base schema: {args.schema}")

        print(f"Starting new evolution run")
        print(f"  Generations: {args.generations}")
        print(f"  Branches/gen: {args.branches}")
        print(f"  Runs/variant: {args.runs}")
        print(f"  Ticks/run: {args.ticks}")
        print(f"  Top-K: {args.top_k}")
        print(f"  Evolver: {logger_msg}")

        runner = EvolutionRunner.create(
            config=evolution_config,
            evolver=evolver,
            engine_factory=engine_factory,
            base_schema=base_schema,
            base_dir=args.evolution_dir,
            interactive=args.interactive,
            data_dir=args.data_dir,
        )

    try:
        runner.run()
    except KeyboardInterrupt:
        print("\n\nEvolution interrupted. Progress saved to tree.json.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
