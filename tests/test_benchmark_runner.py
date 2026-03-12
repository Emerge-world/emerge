"""Tests for run_benchmark.py."""

import json
from types import SimpleNamespace


def _load():
    import importlib
    import run_benchmark

    importlib.reload(run_benchmark)
    return run_benchmark


def test_build_run_command_includes_scarcity_and_benchmark_flags():
    rb = _load()
    cmd = rb.build_run_command(
        benchmark_id="scarcity_v1_demo",
        candidate_label="candidate",
        scenario_id="mild",
        seed=11,
        agents=3,
        ticks=40,
        width=15,
        height=15,
        no_llm=True,
        scarcity={
            "initial_resource_scale": 0.6,
            "regen_chance_scale": 0.8,
            "regen_amount_scale": 0.8,
        },
    )

    assert cmd[:3] == ["uv", "run", "main.py"]
    assert "--benchmark-version" in cmd
    assert "--scenario-id" in cmd
    assert "--initial-resource-scale" in cmd
    assert "--run-id" in cmd
    assert "--no-llm" in cmd


def test_run_benchmark_writes_manifest_and_calls_report(tmp_path, monkeypatch):
    rb = _load()
    suite_path = tmp_path / "scarcity_v1.yaml"
    suite_path.write_text(
        """
benchmark_version: scarcity_v1
defaults:
  agents: 3
  ticks: 40
  width: 15
  height: 15
  no_llm: true
  seeds: [11, 22]
scenarios:
  - id: mild
    scarcity:
      initial_resource_scale: 0.6
      regen_chance_scale: 0.8
      regen_amount_scale: 0.8
""",
        encoding="utf-8",
    )

    calls = []

    def fake_run(cmd, cwd=None):
        calls.append((cmd, cwd))
        return SimpleNamespace(returncode=0)

    reported = {}

    def fake_report(benchmark_dir):
        reported["benchmark_dir"] = str(benchmark_dir)
        return {"overall_verdict": "flat", "matched_pairs": 0, "scenarios": []}

    monkeypatch.setattr(rb.subprocess, "run", fake_run)
    monkeypatch.setattr(rb, "build_benchmark_report", fake_report)
    monkeypatch.chdir(tmp_path)

    benchmark_dir = rb.run_benchmark(suite_path, candidate_label="candidate", max_runs=1)

    manifest = json.loads((benchmark_dir / "manifest.json").read_text())
    assert manifest["benchmark_version"] == "scarcity_v1"
    assert manifest["candidate_label"] == "candidate"
    assert manifest["runs"][0]["status"] == "completed"
    assert len(calls) == 1
    assert reported["benchmark_dir"] == str(benchmark_dir)


def test_run_benchmark_records_failed_runs(tmp_path, monkeypatch):
    rb = _load()
    suite_path = tmp_path / "scarcity_v1.yaml"
    suite_path.write_text(
        """
benchmark_version: scarcity_v1
defaults:
  agents: 3
  ticks: 40
  width: 15
  height: 15
  no_llm: true
  seeds: [11]
scenarios:
  - id: mild
    scarcity:
      initial_resource_scale: 0.6
      regen_chance_scale: 0.8
      regen_amount_scale: 0.8
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(rb.subprocess, "run", lambda cmd, cwd=None: SimpleNamespace(returncode=2))
    monkeypatch.setattr(rb, "build_benchmark_report", lambda benchmark_dir: {"overall_verdict": "flat"})
    monkeypatch.chdir(tmp_path)

    benchmark_dir = rb.run_benchmark(suite_path, candidate_label="candidate")

    manifest = json.loads((benchmark_dir / "manifest.json").read_text())
    assert manifest["runs"][0]["status"] == "failed"
    assert manifest["runs"][0]["exit_code"] == 2
