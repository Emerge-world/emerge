"""Tests for simulation/benchmark_report.py."""

import json

import pytest

from simulation.benchmark_report import build_benchmark_report


def test_build_benchmark_report_marks_candidate_as_improved(tmp_path):
    benchmark_dir = tmp_path / "benchmarks" / "scarcity_v1_demo"
    benchmark_dir.mkdir(parents=True)
    (benchmark_dir / "manifest.json").write_text(
        json.dumps(
            {
                "benchmark_id": "scarcity_v1_demo",
                "benchmark_version": "scarcity_v1",
                "candidate_label": "candidate",
                "baseline_label": "baseline",
                "runs": [
                    {
                        "scenario_id": "mild",
                        "seed": 11,
                        "role": "baseline",
                        "status": "completed",
                        "scarcity_metrics": {
                            "survival_auc": 0.40,
                            "starvation_pressure": 0.80,
                            "food_conversion_efficiency": 0.30,
                        },
                    },
                    {
                        "scenario_id": "mild",
                        "seed": 11,
                        "role": "candidate",
                        "status": "completed",
                        "scarcity_metrics": {
                            "survival_auc": 0.65,
                            "starvation_pressure": 0.45,
                            "food_conversion_efficiency": 0.55,
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_benchmark_report(benchmark_dir)

    assert report["overall_verdict"] == "improved"
    assert report["matched_pairs"] == 1
    assert report["scenarios"][0]["scenario_id"] == "mild"
    assert report["scenarios"][0]["verdict"] == "improved"
    assert report["scenarios"][0]["delta"]["survival_auc"] == 0.25
    assert (benchmark_dir / "reports" / "candidate_summary.json").exists()
    assert (benchmark_dir / "reports" / "baseline_comparison.json").exists()
    assert (benchmark_dir / "reports" / "summary.md").exists()


def test_build_benchmark_report_ignores_failed_runs(tmp_path):
    benchmark_dir = tmp_path / "benchmarks" / "scarcity_v1_demo"
    benchmark_dir.mkdir(parents=True)
    (benchmark_dir / "manifest.json").write_text(
        json.dumps(
            {
                "benchmark_id": "scarcity_v1_demo",
                "benchmark_version": "scarcity_v1",
                "candidate_label": "candidate",
                "baseline_label": "baseline",
                "runs": [
                    {
                        "scenario_id": "mild",
                        "seed": 11,
                        "role": "baseline",
                        "status": "failed",
                    },
                    {
                        "scenario_id": "mild",
                        "seed": 11,
                        "role": "candidate",
                        "status": "completed",
                        "scarcity_metrics": {
                            "survival_auc": 0.65,
                            "starvation_pressure": 0.45,
                            "food_conversion_efficiency": 0.55,
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_benchmark_report(benchmark_dir)

    assert report["matched_pairs"] == 0
    assert report["overall_verdict"] == "flat"


def test_build_benchmark_report_requires_manifest(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_benchmark_report(tmp_path / "missing")
