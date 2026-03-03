#!/usr/bin/env python3
"""
Main entry point for the agent-based life simulation.

Usage:
    python main.py                          # Run with default values
    python main.py --agents 5 --ticks 50    # 5 agents, 50 ticks
    python main.py --no-llm                 # Mode without LLM (rule-based fallback)
    python main.py --seed 42                # Reproducible world
"""

import argparse
import logging
import sys

from simulation.engine import SimulationEngine
from simulation.config import WORLD_START_HOUR


def setup_logging(verbose: bool = False):
    """Configure the logging system."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(description="Autonomous agent life simulation (LLM)")
    parser.add_argument("--agents", type=int, default=3, help="Number of agents (max 5)")
    parser.add_argument("--ticks", type=int, default=100, help="Maximum number of ticks")
    parser.add_argument("--seed", type=int, default=None, help="Seed for the world (reproducibility)")
    parser.add_argument("--no-llm", action="store_true", help="Run without LLM (rule-based fallback mode)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed logging")
    parser.add_argument("--save-log", action="store_true", help="Save log on completion")
    parser.add_argument("--save-state", action="store_true", help="Save world state on completion")
    parser.add_argument("--audit", action="store_true", help="Record behavioral audit data for prompt A/B testing")
    parser.add_argument("--start-hour", type=int, default=WORLD_START_HOUR,
                        help=f"In-world hour the simulation starts at (0-23, default: {WORLD_START_HOUR})")

    args = parser.parse_args()
    setup_logging(args.verbose)

    print("🧬 Starting autonomous agent life simulation...\n")

    engine = SimulationEngine(
        num_agents=args.agents,
        world_seed=args.seed,
        use_llm=not args.no_llm,
        max_ticks=args.ticks,
        audit=args.audit,
        start_hour=args.start_hour,
    )

    try:
        engine.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Simulation interrupted by user.")

    if args.save_log:
        engine.save_world_log()
        print("📝 Log saved to simulation_log.txt")

    if args.save_state:
        engine.save_world_state()
        print("💾 State saved to world_state.json")


if __name__ == "__main__":
    main()
