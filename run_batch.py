#!/usr/bin/env python3
"""
Batch experiment runner for Emerge.

Usage:
    uv run run_batch.py [config.yaml] [--dry-run]

Defaults to experiments.yaml if no config is specified.
"""

import argparse
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not found. Run: uv add pyyaml", file=sys.stderr)
    sys.exit(1)

VALID_KEYS = {"name", "seed", "agents", "ticks", "model", "no_llm", "wandb", "runs", "width", "height"}


def validate_experiments(experiments: list[dict]) -> None:
    """Validate all experiment configs. Exits on error."""
    for i, exp in enumerate(experiments):
        if "name" not in exp:
            print(f"ERROR: experiment #{i + 1} is missing required field 'name'", file=sys.stderr)
            sys.exit(1)
        unknown = set(exp.keys()) - VALID_KEYS
        if unknown:
            print(
                f"ERROR: experiment '{exp.get('name', f'#{i+1}')}' has unknown keys: {sorted(unknown)}",
                file=sys.stderr,
            )
            sys.exit(1)


def expand_experiments(experiments: list[dict]) -> list[dict]:
    """Expand experiments with runs > 1 into individual entries."""
    expanded = []
    for exp in experiments:
        runs = exp.get("runs", 1)
        base = {k: v for k, v in exp.items() if k != "runs"}
        if runs == 1:
            expanded.append(base)
        else:
            for i in range(1, runs + 1):
                entry = {**base, "name": f"{base['name']}_run{i}"}
                expanded.append(entry)
    return expanded


def build_command(exp: dict) -> list[str]:
    """Build the uv run main.py command for one experiment."""
    cmd = ["uv", "run", "main.py"]

    if "agents" in exp:
        cmd += ["--agents", str(exp["agents"])]
    if "ticks" in exp:
        cmd += ["--ticks", str(exp["ticks"])]
    if "seed" in exp:
        cmd += ["--seed", str(exp["seed"])]
    if "model" in exp:
        cmd += ["--model", exp["model"]]
    if "width" in exp:
        cmd += ["--width", str(exp["width"])]
    if "height" in exp:
        cmd += ["--height", str(exp["height"])]
    if exp.get("no_llm", False):
        cmd.append("--no-llm")

    use_wandb = exp.get("wandb", True)
    if use_wandb:
        cmd.append("--wandb")
        cmd += ["--wandb-run-name", exp["name"]]

    return cmd


def run_batch(config_path: Path, dry_run: bool = False) -> None:
    """Load config and run all experiments sequentially."""
    if not config_path.exists():
        print(f"ERROR: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with config_path.open() as f:
        data = yaml.safe_load(f) or {}

    experiments = data.get("experiments", [])
    if not experiments:
        print("ERROR: no experiments found in config", file=sys.stderr)
        sys.exit(1)

    validate_experiments(experiments)
    runs = expand_experiments(experiments)
    total = len(runs)

    print(f"\nBatch: {total} run(s) from {config_path}\n")

    results: list[tuple[str, str, int]] = []  # (name, status, exit_code)

    for idx, exp in enumerate(runs, start=1):
        name = exp["name"]
        cmd = build_command(exp)
        print(f"[{idx}/{total}] {name}")
        print(f"  $ {' '.join(cmd)}\n")

        if dry_run:
            results.append((name, "DRY-RUN", 0))
            continue

        result = subprocess.run(cmd)
        status = "OK" if result.returncode == 0 else "FAILED"
        results.append((name, status, result.returncode))

        if status == "FAILED":
            print(f"\n  WARNING: '{name}' exited with code {result.returncode} — skipping.\n")
        print()

    _print_summary(results)


def _print_summary(results: list[tuple[str, str, int]]) -> None:
    """Print a summary table of all runs."""
    print("\n" + "=" * 60)
    print(f"{'RUN NAME':<40} {'STATUS':<10} {'EXIT'}")
    print("-" * 60)
    for name, status, code in results:
        print(f"{name:<40} {status:<10} {code}")
    print("=" * 60)

    failed = [r for r in results if r[1] == "FAILED"]
    if failed:
        print(f"\n{len(failed)} run(s) failed.")
    else:
        print("\nAll runs completed successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a batch of Emerge experiments")
    parser.add_argument(
        "config",
        nargs="?",
        default="experiments.yaml",
        help="Path to YAML experiment config (default: experiments.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them",
    )
    args = parser.parse_args()
    run_batch(Path(args.config), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
