#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

from run_batch import build_command
from simulation.cohort_analyzer import CohortSummary, summarize_cohort
from simulation.decision_builder import build_decision_artifact
from simulation.experiment_compare import compare_to_baseline
from simulation.experiment_loader import RunMetricsResult, load_run_metrics
from simulation.experiment_policy import CandidateDecision, evaluate_candidate
from simulation.experiment_prioritizer import rank_candidates
from simulation.experiment_schemas import CohortConfig, ExperimentSuite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run experiment gating and prioritization")
    parser.add_argument("config")
    parser.add_argument("--output-dir", default="data/experiments")
    return parser


def _load_suites(config_path: Path) -> list[ExperimentSuite]:
    with Path(config_path).open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    if "suites" in data:
        raw_suites = data["suites"]
    elif "suite" in data:
        raw_suites = [data["suite"]]
    else:
        raw_suites = [data]

    return [ExperimentSuite.model_validate(raw_suite) for raw_suite in raw_suites]


def _current_run_dirs(repo_root: Path) -> set[Path]:
    runs_root = repo_root / "data" / "runs"
    if not runs_root.exists():
        return set()
    return {path for path in runs_root.iterdir() if path.is_dir()}


def _run_experiment(exp: dict, repo_root: Path) -> RunMetricsResult:
    before = _current_run_dirs(repo_root)
    result = subprocess.run(build_command(exp), cwd=repo_root)
    after = _current_run_dirs(repo_root)
    new_run_dirs = sorted(after - before, key=lambda path: path.stat().st_mtime)

    if not new_run_dirs:
        return RunMetricsResult(
            run_dir=repo_root / "data" / "runs" / f"missing_{exp['name']}",
            invalid=True,
        )

    run_result = load_run_metrics(new_run_dirs[-1])
    if result.returncode != 0:
        run_result.invalid = True
    return run_result


def _run_cohort(suite: ExperimentSuite, cohort: CohortConfig, repo_root: Path) -> list[RunMetricsResult]:
    runs = []
    for seed in suite.seed_set:
        exp = dict(cohort.config)
        exp["seed"] = seed
        exp["name"] = f"{suite.name}_{cohort.name}_seed{seed}"
        runs.append(_run_experiment(exp, repo_root))
    return runs


def _priority_input(
    candidate: CohortSummary,
    comparison: dict,
    decision: CandidateDecision,
) -> dict:
    upside = max((max(0.0, item["delta"]) for item in comparison.values()), default=0.0)
    uncertainty = round(candidate.invalid_run_rate + (1 / max(candidate.run_count, 1)), 4)
    strategic_value = 1.0 if decision.decision == "inconclusive" else 0.5
    return {
        "name": candidate.name,
        "decision": decision.decision,
        "uncertainty": uncertainty,
        "upside": round(upside, 4),
        "strategic_value": strategic_value,
    }


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def execute_suite(suite: ExperimentSuite, output_dir: Path, repo_root: Path) -> None:
    suite_output_dir = Path(output_dir) / suite.name
    suite_output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(suite_output_dir / "suite.json", suite.model_dump())

    baseline_runs = _run_cohort(suite, suite.baseline, repo_root)
    baseline_summary = summarize_cohort(suite.baseline.name, baseline_runs)
    _write_json(suite_output_dir / "cohorts" / f"{suite.baseline.name}.json", asdict(baseline_summary))

    priorities = []
    for candidate_config in suite.candidates:
        candidate_runs = _run_cohort(suite, candidate_config, repo_root)
        candidate_summary = summarize_cohort(candidate_config.name, candidate_runs)
        _write_json(
            suite_output_dir / "cohorts" / f"{candidate_config.name}.json",
            asdict(candidate_summary),
        )

        comparison = compare_to_baseline(baseline_summary, candidate_summary)
        decision = evaluate_candidate(
            comparison=comparison,
            candidate_invalid_run_rate=candidate_summary.invalid_run_rate,
            primary_metrics=suite.metrics.primary,
            tolerances={metric: -0.05 for metric in suite.metrics.primary},
            max_invalid_run_rate=suite.policy.max_invalid_run_rate,
            min_effect_size=suite.policy.min_effect_size,
        )
        build_decision_artifact(
            suite.model_dump(),
            asdict(baseline_summary),
            asdict(candidate_summary),
            suite_output_dir / "decisions" / f"{candidate_config.name}.json",
        )
        priorities.append(_priority_input(candidate_summary, comparison, decision))

    ranked = rank_candidates(priorities)
    _write_json(suite_output_dir / "priorities.json", ranked)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: config file not found: {config_path}", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parent
    suites = _load_suites(config_path)
    output_dir = Path(args.output_dir)

    for suite in suites:
        print(f"Running suite: {suite.name}")
        execute_suite(suite, output_dir, repo_root)
        print(f"  -> wrote artifacts to {output_dir / suite.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
