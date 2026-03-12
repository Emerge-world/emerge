"""Build aggregate benchmark comparison reports."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any

_METRIC_DIRECTIONS = {
    "survival_auc": "higher",
    "starvation_pressure": "lower",
    "food_conversion_efficiency": "higher",
}


def build_benchmark_report(benchmark_dir: Path | str) -> dict:
    """Read manifest.json, build comparison outputs, and return the comparison dict."""

    benchmark_path = Path(benchmark_dir)
    manifest_path = benchmark_path / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"benchmark manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_manifest(manifest)

    completed_runs = [
        run for run in manifest.get("runs", [])
        if run.get("status", "completed") == "completed"
    ]

    matched_pairs = _collect_matched_pairs(completed_runs, benchmark_path)
    scenario_rows = _build_scenario_rows(matched_pairs)
    overall_verdict = _summarize_verdicts([row["verdict"] for row in scenario_rows])

    candidate_summary = {
        "benchmark_id": manifest["benchmark_id"],
        "benchmark_version": manifest["benchmark_version"],
        "candidate_label": manifest["candidate_label"],
        "baseline_label": manifest["baseline_label"],
        "total_runs": len(manifest.get("runs", [])),
        "completed_runs": len(completed_runs),
        "failed_runs": sum(1 for run in manifest.get("runs", []) if run.get("status") == "failed"),
        "matched_pairs": len(matched_pairs),
    }
    comparison = {
        "benchmark_id": manifest["benchmark_id"],
        "benchmark_version": manifest["benchmark_version"],
        "candidate_label": manifest["candidate_label"],
        "baseline_label": manifest["baseline_label"],
        "matched_pairs": len(matched_pairs),
        "overall_verdict": overall_verdict,
        "scenarios": scenario_rows,
    }

    reports_dir = benchmark_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "candidate_summary.json").write_text(
        json.dumps(candidate_summary, indent=2),
        encoding="utf-8",
    )
    (reports_dir / "baseline_comparison.json").write_text(
        json.dumps(comparison, indent=2),
        encoding="utf-8",
    )
    (reports_dir / "summary.md").write_text(
        _render_summary(candidate_summary, comparison),
        encoding="utf-8",
    )

    return comparison


def _validate_manifest(manifest: dict[str, Any]) -> None:
    required = ("benchmark_id", "benchmark_version", "candidate_label", "baseline_label", "runs")
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ValueError(f"manifest missing required keys: {', '.join(missing)}")
    if not isinstance(manifest["runs"], list):
        raise ValueError("manifest.runs must be a list")


def _collect_matched_pairs(runs: list[dict], benchmark_dir: Path) -> list[dict]:
    grouped: dict[tuple[str, int], dict[str, dict]] = {}
    for run in runs:
        scenario_id = run.get("scenario_id")
        seed = run.get("seed")
        role = run.get("role")
        if not scenario_id or seed is None or role not in {"baseline", "candidate"}:
            continue
        metrics = _load_scarcity_metrics(run, benchmark_dir)
        if metrics is None:
            continue
        grouped.setdefault((scenario_id, int(seed)), {})[role] = metrics

    matched = []
    for (scenario_id, seed), role_map in sorted(grouped.items()):
        baseline = role_map.get("baseline")
        candidate = role_map.get("candidate")
        if baseline is None or candidate is None:
            continue
        matched.append({
            "scenario_id": scenario_id,
            "seed": seed,
            "baseline": baseline,
            "candidate": candidate,
        })
    return matched


def _load_scarcity_metrics(run: dict, benchmark_dir: Path) -> dict | None:
    if "scarcity_metrics" in run:
        return dict(run["scarcity_metrics"])

    run_dir = run.get("run_dir")
    if not run_dir:
        return None

    run_path = Path(run_dir)
    if not run_path.is_absolute():
        run_path = (benchmark_dir / run_path).resolve()

    scarcity_path = run_path / "metrics" / "scarcity.json"
    if not scarcity_path.exists():
        return None
    return json.loads(scarcity_path.read_text(encoding="utf-8"))


def _build_scenario_rows(matched_pairs: list[dict]) -> list[dict]:
    by_scenario: dict[str, list[dict]] = {}
    for pair in matched_pairs:
        by_scenario.setdefault(pair["scenario_id"], []).append(pair)

    rows = []
    for scenario_id in sorted(by_scenario):
        pairs = by_scenario[scenario_id]
        baseline_metrics = {
            metric: [pair["baseline"][metric] for pair in pairs]
            for metric in _METRIC_DIRECTIONS
        }
        candidate_metrics = {
            metric: [pair["candidate"][metric] for pair in pairs]
            for metric in _METRIC_DIRECTIONS
        }
        delta = {
            metric: round(median(candidate_metrics[metric]) - median(baseline_metrics[metric]), 4)
            for metric in _METRIC_DIRECTIONS
        }
        verdict = _verdict_for_delta(delta)
        rows.append({
            "scenario_id": scenario_id,
            "pairs": len(pairs),
            "baseline": {metric: round(median(values), 4) for metric, values in baseline_metrics.items()},
            "candidate": {metric: round(median(values), 4) for metric, values in candidate_metrics.items()},
            "delta": delta,
            "verdict": verdict,
        })
    return rows


def _verdict_for_delta(delta: dict[str, float]) -> str:
    wins = 0
    losses = 0
    for metric, change in delta.items():
        direction = _METRIC_DIRECTIONS[metric]
        if change == 0:
            continue
        improved = change > 0 if direction == "higher" else change < 0
        if improved:
            wins += 1
        else:
            losses += 1

    if wins > losses:
        return "improved"
    if losses > wins:
        return "regressed"
    return "flat"


def _summarize_verdicts(verdicts: list[str]) -> str:
    improved = sum(1 for verdict in verdicts if verdict == "improved")
    regressed = sum(1 for verdict in verdicts if verdict == "regressed")
    if improved > regressed:
        return "improved"
    if regressed > improved:
        return "regressed"
    return "flat"


def _render_summary(candidate_summary: dict, comparison: dict) -> str:
    lines = [
        f"# Benchmark Summary: {comparison['benchmark_id']}",
        "",
        f"- Version: `{comparison['benchmark_version']}`",
        f"- Candidate: `{comparison['candidate_label']}`",
        f"- Baseline: `{comparison['baseline_label']}`",
        f"- Matched pairs: {comparison['matched_pairs']}",
        f"- Overall verdict: **{comparison['overall_verdict']}**",
        "",
        "## Scenarios",
        "",
    ]
    if not comparison["scenarios"]:
        lines.append("No matched completed baseline/candidate pairs were available.")
    else:
        for row in comparison["scenarios"]:
            lines.extend(
                [
                    f"### {row['scenario_id']}",
                    f"- Verdict: `{row['verdict']}`",
                    f"- Pairs: {row['pairs']}",
                    f"- Delta survival_auc: {row['delta']['survival_auc']}",
                    f"- Delta starvation_pressure: {row['delta']['starvation_pressure']}",
                    f"- Delta food_conversion_efficiency: {row['delta']['food_conversion_efficiency']}",
                    "",
                ]
            )
    return "\n".join(lines) + "\n"
