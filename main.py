#!/usr/bin/env python3
"""
Main entry point for the agent-based life simulation.

Usage:
    python main.py                          # Run with infinite ticks by default
    python main.py --agents 5 --ticks 50    # 5 agents, 50 ticks
    python main.py --ticks infinite         # Explicit infinite run
    python main.py --no-llm                 # Mode without LLM (rule-based fallback)
    python main.py --seed 42                # Reproducible world
"""

import argparse
import logging
import sys

from simulation.engine import SimulationEngine
from simulation.config import WORLD_START_HOUR, WORLD_WIDTH, WORLD_HEIGHT
from pathlib import Path
from simulation.wandb_logger import WandbLogger
from simulation import config as sim_config
from simulation.tick_limits import parse_tick_limit_arg


def setup_logging(verbose: bool = False):
    """Configure the logging system."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous agent life simulation (LLM)")
    parser.add_argument("--agents", type=int, default=3, help="Number of agents (max 5)")
    parser.add_argument(
        "--ticks",
        type=parse_tick_limit_arg,
        default=sim_config.MAX_TICKS,
        help="Maximum number of ticks (positive integer or 'infinite'; default: infinite)",
    )
    parser.add_argument("--seed", type=int, default=None, help="Seed for the world (reproducibility)")
    parser.add_argument("--no-llm", action="store_true", help="Run without LLM (rule-based fallback mode)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed logging")
    parser.add_argument("--save-log", action="store_true", help="Save log on completion")
    parser.add_argument("--save-state", action="store_true", help="Save world state on completion")
    parser.add_argument("--start-hour", type=int, default=WORLD_START_HOUR,
                        help=f"In-world hour the simulation starts at (0-23, default: {WORLD_START_HOUR})")
    parser.add_argument("--width",  type=int, default=WORLD_WIDTH,  help=f"World width in tiles (default: {WORLD_WIDTH})")
    parser.add_argument("--height", type=int, default=WORLD_HEIGHT, help=f"World height in tiles (default: {WORLD_HEIGHT})")
    parser.add_argument("--wandb", action="store_true",
                        help="Enable Weights & Biases experiment logging")
    parser.add_argument("--wandb-project", default="emerge",
                        help="W&B project name (default: emerge)")
    parser.add_argument("--wandb-entity", default=None,
                        help="W&B entity/team (default: your W&B account)")
    parser.add_argument("--wandb-run-name", default=None,
                        help="W&B run name (useful for batch experiments)")
    parser.add_argument("--model", default=None,
                        help=f"vllm model to use (default: {sim_config.VLLM_MODEL})")
    parser.add_argument("--no-digest", action="store_true",
                        help="Skip LLM digest generation after run")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    wandb_logger = None
    if args.wandb:
        run_config = {
            "agents": args.agents,
            "ticks": args.ticks,
            "seed": args.seed,
            "no_llm": args.no_llm,
            "width": args.width,
            "height": args.height,
            "start_hour": args.start_hour,
            "LLM_MODEL": args.model or sim_config.VLLM_MODEL,
            "LLM_TEMPERATURE": sim_config.LLM_TEMPERATURE,
            "MOVE_ENERGY_COST": sim_config.ENERGY_COST_MOVE,
            "REST_ENERGY_GAIN": sim_config.ENERGY_RECOVERY_REST,
            "INNOVATE_ENERGY_COST": sim_config.ENERGY_COST_INNOVATE,
            "MAX_HUNGER": sim_config.AGENT_MAX_HUNGER,
            "HUNGER_DAMAGE": sim_config.HUNGER_DAMAGE_PER_TICK,
            "LIFE_MAX": sim_config.AGENT_MAX_LIFE,
            "ENERGY_MAX": sim_config.AGENT_MAX_ENERGY,
            "MEMORY_EPISODIC_MAX": sim_config.MEMORY_EPISODIC_MAX,
            "MEMORY_SEMANTIC_MAX": sim_config.MEMORY_SEMANTIC_MAX,
            "MEMORY_COMPRESSION_INTERVAL": sim_config.MEMORY_COMPRESSION_INTERVAL,
        }
        prompts_dir = Path(__file__).parent / "prompts"
        wandb_logger = WandbLogger(
            project=args.wandb_project,
            entity=args.wandb_entity,
            run_config=run_config,
            prompts_dir=prompts_dir,
            run_name=args.wandb_run_name,
        )

    print("🧬 Starting autonomous agent life simulation...\n")

    engine = SimulationEngine(
        num_agents=args.agents,
        world_seed=args.seed,
        use_llm=not args.no_llm,
        max_ticks=args.ticks,
        start_hour=args.start_hour,
        world_width=args.width,
        world_height=args.height,
        wandb_logger=wandb_logger,
        ollama_model=args.model,
        run_digest=not args.no_digest,
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
