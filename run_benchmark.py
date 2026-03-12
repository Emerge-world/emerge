#!/usr/bin/env python3
"""Run a frozen scarcity benchmark suite and build its report."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

from simulation.benchmark_report import build_benchmark_report
from simulation.benchmark_suite import BenchmarkSuite, load_benchmark_suite


def build_run_command(
    *,
    benchmark_id: str,
    candidate_label: str,
    scenario_id: str,
    seed: int,
    agents: int,
    ticks: int,
    width: int,
    height: int,
    no_llm: bool,
    scarcity: dict[str, float],
    benchmark_version: str = "scarcity_v1",
    model: str | None = None,
    baseline_label: str | None = None,
) -> list[str]:
    """Build the main.py command for one scenario/seed run."""

    run_id = f"{benchmark_id}__{candidate_label}__{scenario_id}__seed{seed}"
    cmd = [
        "uv",
        "run",
        "main.py",
        "--run-id",
        run_id,
        "--seed",
        str(seed),
        "--agents",
        str(agents),
        "--ticks",
        str(ticks),
        "--width",
        str(width),
        "--height",
        str(height),
        "--benchmark-id",
        benchmark_id,
        "--benchmark-version",
        benchmark_version,
        "--scenario-id",
        scenario_id,
        "--candidate-label",
        candidate_label,
        "--initial-resource-scale",
        str(scarcity["initial_resource_scale"]),
        "--regen-chance-scale",
        str(scarcity["regen_chance_scale"]),
        "--regen-amount-scale",
        str(scarcity["regen_amount_scale"]),
    ]
    if baseline_label:
        cmd.extend(["--baseline-label", baseline_label])
    if no_llm:
        cmd.append("--no-llm")
    if model:
        cmd.extend(["--model", model])
    return cmd


def run_benchmark(
    suite_path: Path | str,
    *,
    candidate_label: str,
    baseline_manifest: Path | str | None = None,
    benchmark_id: str | None = None,
    baseline_label: str | None = None,
    max_runs: int | None = None,
    dry_run: bool = False,
) -> Path:
    """Execute a benchmark suite sequentially and build reports."""

    suite = load_benchmark_suite(suite_path)
    benchmark_id = benchmark_id or _default_benchmark_id(suite, candidate_label)
    benchmark_dir = Path("data") / "benchmarks" / benchmark_id
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    (benchmark_dir / "runs").mkdir(exist_ok=True)

    manifest = {
        "benchmark_id": benchmark_id,
        "benchmark_version": suite.benchmark_version,
        "candidate_label": candidate_label,
        "baseline_label": baseline_label or "baseline",
        "created_at": dt.datetime.now().isoformat() + "Z",
        "suite_path": str(Path(suite.path).resolve()),
        "runs": [],
    }

    if baseline_manifest:
        imported_label, baseline_runs = _load_baseline_runs(Path(baseline_manifest), suite.benchmark_version)
        manifest["baseline_label"] = baseline_label or imported_label
        manifest["runs"].extend(baseline_runs)

    _write_manifest(benchmark_dir, manifest)

    repo_root = Path(__file__).resolve().parent
    run_count = 0
    for scenario in suite.scenarios:
        for seed in suite.defaults.seeds:
            if max_runs is not None and run_count >= max_runs:
                break
            cmd = build_run_command(
                benchmark_id=benchmark_id,
                benchmark_version=suite.benchmark_version,
                candidate_label=candidate_label,
                baseline_label=manifest["baseline_label"],
                scenario_id=scenario.id,
                seed=seed,
                agents=suite.defaults.agents,
                ticks=suite.defaults.ticks,
                width=suite.defaults.width,
                height=suite.defaults.height,
                no_llm=suite.defaults.no_llm,
                scarcity=scenario.scarcity,
                model=suite.defaults.model,
            )
            run_id = _extract_run_id(cmd)
            entry = {
                "run_id": run_id,
                "scenario_id": scenario.id,
                "scenario_label": scenario.label,
                "seed": seed,
                "role": "candidate",
                "status": "dry-run" if dry_run else "pending",
                "exit_code": None,
                "run_dir": str((repo_root / "data" / "runs" / run_id).resolve()),
                "command": cmd,
                "scarcity": scenario.scarcity,
            }

            if dry_run:
                entry["status"] = "dry-run"
            else:
                result = subprocess.run(cmd, cwd=repo_root)
                entry["exit_code"] = result.returncode
                entry["status"] = "completed" if result.returncode == 0 else "failed"
                scarcity_metrics_path = repo_root / "data" / "runs" / run_id / "metrics" / "scarcity.json"
                if scarcity_metrics_path.exists():
                    entry["scarcity_metrics"] = json.loads(scarcity_metrics_path.read_text(encoding="utf-8"))

            manifest["runs"].append(entry)
            _write_manifest(benchmark_dir, manifest)
            run_count += 1
        if max_runs is not None and run_count >= max_runs:
            break

    build_benchmark_report(benchmark_dir)
    return benchmark_dir


def _load_baseline_runs(manifest_path: Path, benchmark_version: str) -> tuple[str, list[dict]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("benchmark_version") != benchmark_version:
        raise ValueError(
            f"baseline manifest benchmark_version {manifest.get('benchmark_version')} does not match {benchmark_version}"
        )

    imported_label = manifest.get("candidate_label") or manifest.get("baseline_label") or "baseline"
    baseline_runs = []
    for run in manifest.get("runs", []):
        if run.get("role") != "candidate":
            continue
        copied = dict(run)
        copied["role"] = "baseline"
        baseline_runs.append(copied)
    return imported_label, baseline_runs


def _write_manifest(benchmark_dir: Path, manifest: dict) -> None:
    (benchmark_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _default_benchmark_id(suite: BenchmarkSuite, candidate_label: str) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{suite.benchmark_version}__{candidate_label}__{stamp}"


def _extract_run_id(cmd: list[str]) -> str:
    run_id_index = cmd.index("--run-id") + 1
    return cmd[run_id_index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a scarcity benchmark suite")
    parser.add_argument("suite", help="Path to benchmark suite YAML")
    parser.add_argument("--candidate-label", required=True, help="Candidate label for this benchmark batch")
    parser.add_argument("--baseline-manifest", default=None, help="Optional prior manifest.json to compare against")
    parser.add_argument("--baseline-label", default=None, help="Override the label shown for the baseline batch")
    parser.add_argument("--benchmark-id", default=None, help="Override the generated benchmark batch id")
    parser.add_argument("--max-runs", type=int, default=None, help="Limit scenario/seed runs for smoke testing")
    parser.add_argument("--dry-run", action="store_true", help="Write the manifest without executing runs")
    args = parser.parse_args()

    benchmark_dir = run_benchmark(
        args.suite,
        candidate_label=args.candidate_label,
        baseline_manifest=args.baseline_manifest,
        baseline_label=args.baseline_label,
        benchmark_id=args.benchmark_id,
        max_runs=args.max_runs,
        dry_run=args.dry_run,
    )
    print(f"Benchmark artifacts written to {benchmark_dir}")


if __name__ == "__main__":
    main()
