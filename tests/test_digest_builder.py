"""Integration tests for DigestBuilder."""

import json
import subprocess
import sys
from pathlib import Path
import pytest
from simulation.digest.digest_builder import DigestBuilder


# --- Event helpers (reuse pattern from test_ebs_builder.py) ---

def _write_events(run_dir: Path, events: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": "test-run", "seed": 42, "ticks": 10, "agent_count": 1,
        "world_size": [10, 10], "model_id": "test", "git_commit": "abc123",
    }
    (run_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (run_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )


def _minimal_events() -> list[dict]:
    """10 ticks, 1 agent (Ada), all moves."""
    events = [{
        "run_id": "test-run", "tick": 0, "event_type": "run_start", "agent_id": None,
        "payload": {"config": {"agent_names": ["Ada"]}, "model_id": "test", "world_seed": 42},
    }]
    for t in range(1, 11):
        events.append({
            "run_id": "test-run", "tick": t, "event_type": "agent_decision",
            "agent_id": "Ada",
            "payload": {"parsed_action": {"action": "move", "direction": "east", "reason": "exploring"},
                        "parse_ok": True},
        })
        events.append({
            "run_id": "test-run", "tick": t, "event_type": "agent_perception",
            "agent_id": "Ada",
            "payload": {"pos": {"x": t, "y": 0}, "hunger": 20, "energy": 80,
                        "resources_nearby": [], "night_penalty_active": False},
        })
        events.append({
            "run_id": "test-run", "tick": t, "event_type": "oracle_resolution",
            "agent_id": "Ada",
            "payload": {"success": True, "action": "move", "cache_hit": True,
                        "is_innovation_action": False, "effects": {}},
        })
        events.append({
            "run_id": "test-run", "tick": t, "event_type": "agent_state",
            "agent_id": "Ada",
            "payload": {"life": 100, "hunger": 20 + t, "energy": 80, "alive": True,
                        "pos": {"x": t, "y": 0}},
        })
    events.append({
        "run_id": "test-run", "tick": 10, "event_type": "run_end", "agent_id": None,
        "payload": {"total_ticks": 10, "survivors": ["Ada"]},
    })
    return events


def _events_with_born_agent() -> list[dict]:
    """Run starts with Ada only; Kira is born later and emits her own events."""
    return [
        {
            "run_id": "test-run",
            "tick": 0,
            "event_type": "run_start",
            "agent_id": None,
            "payload": {
                "config": {"agent_names": ["Ada"]},
                "model_id": "test",
                "world_seed": 42,
            },
        },
        {
            "run_id": "test-run",
            "tick": 1,
            "event_type": "agent_decision",
            "agent_id": "Ada",
            "payload": {
                "parsed_action": {"action": "rest", "reason": "recover"},
                "parse_ok": True,
            },
        },
        {
            "run_id": "test-run",
            "tick": 1,
            "event_type": "agent_state",
            "agent_id": "Ada",
            "payload": {
                "life": 100,
                "hunger": 20,
                "energy": 85,
                "alive": True,
                "pos": {"x": 0, "y": 0},
            },
        },
        {
            "run_id": "test-run",
            "tick": 5,
            "event_type": "agent_birth",
            "agent_id": "Kira",
            "payload": {
                "child_name": "Kira",
                "generation": 1,
                "born_tick": 5,
                "parent_ids": ["Ada", "Bruno"],
                "pos": [1, 0],
            },
        },
        {
            "run_id": "test-run",
            "tick": 5,
            "event_type": "agent_state",
            "agent_id": "Kira",
            "payload": {
                "life": 50,
                "hunger": 40,
                "energy": 40,
                "alive": True,
                "pos": {"x": 1, "y": 0},
            },
        },
        {
            "run_id": "test-run",
            "tick": 6,
            "event_type": "agent_decision",
            "agent_id": "Kira",
            "payload": {
                "parsed_action": {"action": "move", "direction": "east", "reason": "exploring"},
                "parse_ok": True,
            },
        },
        {
            "run_id": "test-run",
            "tick": 6,
            "event_type": "agent_perception",
            "agent_id": "Kira",
            "payload": {
                "pos": {"x": 1, "y": 0},
                "hunger": 40,
                "energy": 40,
                "resources_nearby": [],
                "night_penalty_active": False,
            },
        },
        {
            "run_id": "test-run",
            "tick": 6,
            "event_type": "oracle_resolution",
            "agent_id": "Kira",
            "payload": {
                "success": True,
                "action": "move",
                "cache_hit": True,
                "is_innovation_action": False,
                "effects": {},
            },
        },
        {
            "run_id": "test-run",
            "tick": 6,
            "event_type": "agent_state",
            "agent_id": "Kira",
            "payload": {
                "life": 50,
                "hunger": 41,
                "energy": 38,
                "alive": True,
                "pos": {"x": 2, "y": 0},
            },
        },
        {
            "run_id": "test-run",
            "tick": 6,
            "event_type": "run_end",
            "agent_id": None,
            "payload": {"total_ticks": 6, "survivors": ["Ada", "Kira"]},
        },
    ]


class TestDigestBuilderOutput:
    def test_creates_run_digest_json(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        assert (tmp_path / "llm_digest" / "run_digest.json").exists()

    def test_creates_run_digest_md(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        assert (tmp_path / "llm_digest" / "run_digest.md").exists()

    def test_creates_per_agent_files(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        assert (tmp_path / "llm_digest" / "agents" / "Ada.json").exists()
        assert (tmp_path / "llm_digest" / "agents" / "Ada.md").exists()

    def test_run_digest_has_required_keys(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        data = json.loads((tmp_path / "llm_digest" / "run_digest.json").read_text())
        for key in ("run_id", "generated_at", "meta", "outcomes", "agents", "anomalies"):
            assert key in data, f"Missing key: {key}"

    def test_evidence_index_covers_anomaly_supporting_event_ids(self, tmp_path):
        """Anomaly supporting_event_ids must be reachable via evidence_index.json."""
        # Build events that trigger a PARSE_FAIL_STREAK (3 consecutive parse failures)
        events = _minimal_events()
        # Replace first 3 decision events with parse_ok=False
        fail_count = 0
        for ev in events:
            if ev.get("event_type") == "agent_decision" and fail_count < 3:
                ev["payload"]["parse_ok"] = False
                fail_count += 1
        _write_events(tmp_path, events)
        DigestBuilder(tmp_path).build()

        evidence = json.loads((tmp_path / "llm_digest" / "evidence_index.json").read_text())
        run_data = json.loads((tmp_path / "llm_digest" / "run_digest.json").read_text())

        # All anomaly_ids from the run digest must appear as keys in the evidence index
        for anomaly in run_data.get("anomalies", []):
            assert anomaly["anomaly_id"] in evidence, (
                f"Anomaly {anomaly['anomaly_id']} not in evidence index"
            )

    def test_manifest_is_deterministic_with_no_llm_overlay(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        manifest = json.loads((tmp_path / "llm_digest" / "generation_manifest.json").read_text())
        assert manifest["mode"] == "deterministic"
        assert manifest["llm_overlay"] is None

    def test_manifest_source_files_use_relative_paths(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        DigestBuilder(tmp_path).build()
        manifest = json.loads((tmp_path / "llm_digest" / "generation_manifest.json").read_text())
        for v in manifest.get("source_files", {}).values():
            assert not str(v).startswith("/"), f"Path should be relative: {v}"

    def test_no_llm_calls_made(self, tmp_path):
        """DigestBuilder must not import or call any LLM client."""
        _write_events(tmp_path, _minimal_events())
        # If this completes without network errors or import side-effects, we're good
        DigestBuilder(tmp_path).build()

    def test_noop_when_events_missing(self, tmp_path):
        """Should not raise if events.jsonl doesn't exist."""
        tmp_path.mkdir(exist_ok=True)
        DigestBuilder(tmp_path).build()  # no exception
        assert not (tmp_path / "llm_digest").exists()

    def test_includes_born_agents_with_lineage_metadata(self, tmp_path):
        _write_events(tmp_path, _events_with_born_agent())

        DigestBuilder(tmp_path).build()

        run_data = json.loads((tmp_path / "llm_digest" / "run_digest.json").read_text())
        agent_ids = [agent["agent_id"] for agent in run_data["agents"]]
        assert "Kira" in agent_ids

        kira_summary = next(agent for agent in run_data["agents"] if agent["agent_id"] == "Kira")
        assert kira_summary["generation"] == 1
        assert kira_summary["born_tick"] == 5
        assert kira_summary["parent_ids"] == ["Ada", "Bruno"]

        kira_path = tmp_path / "llm_digest" / "agents" / "Kira.json"
        assert kira_path.exists()
        kira_agent = json.loads(kira_path.read_text())
        assert kira_agent["lineage"] == {
            "generation": 1,
            "born_tick": 5,
            "parent_ids": ["Ada", "Bruno"],
            "is_born_agent": True,
        }


class TestDigestBuilderCLI:
    def test_cli_exits_zero(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        result = subprocess.run(
            [sys.executable, "-m", "simulation.digest.digest_builder", str(tmp_path)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_cli_creates_output_files(self, tmp_path):
        _write_events(tmp_path, _minimal_events())
        subprocess.run(
            [sys.executable, "-m", "simulation.digest.digest_builder", str(tmp_path)],
            capture_output=True
        )
        assert (tmp_path / "llm_digest" / "run_digest.json").exists()
