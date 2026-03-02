"""
Entry point for the Emerge web server.

Usage:
    python server/run_server.py [options]

Options:
    --agents N       Number of agents (default: 3)
    --ticks N        Max ticks to run (default: 500)
    --seed N         World seed for reproducibility
    --no-llm         Run without LLM (fast smoke-test mode)
    --port N         HTTP port (default: 8000)
    --tick-delay F   Seconds between ticks (default: from config)
"""

import sys
import os

# When run as `python server/run_server.py`, Python adds server/ to sys.path
# instead of the project root. Fix that so `server.*` and `simulation.*` resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force UTF-8 on stdout/stderr so emoji in the engine's print() calls don't
# crash on Windows terminals that default to cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import logging

import uvicorn

import server.server as _server
from simulation.engine import SimulationEngine
from simulation import config as sim_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    parser = argparse.ArgumentParser(description="Emerge simulation web server")
    parser.add_argument("--agents", type=int, default=3, help="Number of agents")
    parser.add_argument("--ticks", type=int, default=500, help="Max simulation ticks")
    parser.add_argument("--seed", type=int, default=None, help="World seed")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM, use fallback")
    parser.add_argument("--port", type=int, default=8001, help="HTTP port")
    parser.add_argument(
        "--tick-delay",
        type=float,
        default=None,
        help="Seconds between ticks (overrides config)",
    )
    args = parser.parse_args()

    # Override tick delay if requested
    if args.tick_delay is not None:
        sim_config.TICK_DELAY_SECONDS = args.tick_delay

    print(f"\nEmerge web server")
    print(f"  Agents:    {args.agents}")
    print(f"  Max ticks: {args.ticks}")
    print(f"  Seed:      {args.seed}")
    print(f"  LLM:       {'disabled' if args.no_llm else 'enabled'}")
    print(f"  Port:      {args.port}")
    print(f"\n  Open http://localhost:{args.port} in your browser (or start the UI dev server)\n")

    _server.engine = SimulationEngine(
        num_agents=args.agents,
        world_seed=args.seed,
        use_llm=not args.no_llm,
        max_ticks=args.ticks,
    )

    uvicorn.run(
        _server.app,
        host="0.0.0.0",
        port=args.port,
        log_level="warning",   # reduce uvicorn noise; our own logger handles the rest
    )


if __name__ == "__main__":
    main()
