"""Tests for DigestRenderer — pure serialization and markdown rendering."""

import json
from pathlib import Path
import pytest
from simulation.digest.digest_renderer import DigestRenderer


def _minimal_run_digest() -> dict:
    return {
        "run_id": "test-run",
        "generated_at": "2026-03-11T10:00:00Z",
        "meta": {"seed": 42, "ticks": 10, "agent_count": 1, "world_size": [10, 10],
                 "model_id": "test", "git_commit": "abc123"},
        "outcomes": {"survivors": ["Ada"], "deaths": [], "total_innovations_approved": 0,
                     "total_innovations_attempted": 0, "total_anomalies": 0,
                     "anomaly_counts_by_type": {}},
        "agents": [{"agent_id": "Ada", "status": "alive", "phase_count": 2,
                    "dominant_mode": "exploration", "innovation_count": 0,
                    "anomaly_count": 0, "digest_path": "agents/Ada.json"}],
        "anomalies": [],
        "evidence_path": "evidence_index.json",
        "manifest_path": "generation_manifest.json",
    }


def _minimal_agent_digest() -> dict:
    return {
        "agent_id": "Ada",
        "run_id": "test-run",
        "status": "alive",
        "final_state": {"life": 100, "hunger": 20, "energy": 80, "pos": {"x": 0, "y": 0}},
        "state_extrema": {"min_life": {"value": 90, "tick": 5}, "max_hunger": {"value": 40, "tick": 3}},
        "action_mix": {"move": 0.8, "eat": 0.2},
        "phases": [{"phase_id": 1, "mode": "exploration", "tick_start": 1, "tick_end": 10,
                    "confidence": 0.75, "dominant_signals": ["reason_explore"],
                    "supporting_event_ids": []}],
        "tick_scores": [],
        "innovations": [],
        "contradictions": [],
        "anomalies": [],
        "critical_events": [],
    }


class TestDigestRenderer:
    def test_writes_run_digest_json(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        run_digest = _minimal_run_digest()
        renderer.render(run_digest, agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest={})
        assert (tmp_path / "llm_digest" / "run_digest.json").exists()
        loaded = json.loads((tmp_path / "llm_digest" / "run_digest.json").read_text())
        assert loaded["run_id"] == "test-run"

    def test_writes_run_digest_md(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        run_digest = _minimal_run_digest()
        renderer.render(run_digest, agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest={})
        md = (tmp_path / "llm_digest" / "run_digest.md").read_text()
        assert "test-run" in md
        assert "## Outcomes" in md
        assert "## Agents" in md

    def test_writes_agent_json_and_md(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        run_digest = _minimal_run_digest()
        renderer.render(run_digest, agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest={})
        assert (tmp_path / "llm_digest" / "agents" / "Ada.json").exists()
        assert (tmp_path / "llm_digest" / "agents" / "Ada.md").exists()

    def test_agent_md_contains_sections(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        renderer.render(_minimal_run_digest(),
                        agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest={})
        md = (tmp_path / "llm_digest" / "agents" / "Ada.md").read_text()
        assert "## Phases" in md
        assert "## Innovations" in md
        assert "## Critical Events" in md

    def test_no_none_placeholders_in_md(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        renderer.render(_minimal_run_digest(),
                        agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest={})
        run_md = (tmp_path / "llm_digest" / "run_digest.md").read_text()
        agent_md = (tmp_path / "llm_digest" / "agents" / "Ada.md").read_text()
        assert "None" not in run_md
        assert "None" not in agent_md

    def test_writes_evidence_index(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        evidence = {"Ada_phase_1": ["evt_0001_Ada_agent_decision"]}
        renderer.render(_minimal_run_digest(),
                        agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index=evidence, manifest={})
        loaded = json.loads((tmp_path / "llm_digest" / "evidence_index.json").read_text())
        assert loaded["Ada_phase_1"] == ["evt_0001_Ada_agent_decision"]

    def test_writes_generation_manifest(self, tmp_path):
        renderer = DigestRenderer(tmp_path)
        manifest = {"mode": "deterministic", "llm_overlay": None}
        renderer.render(_minimal_run_digest(),
                        agent_digests={"Ada": _minimal_agent_digest()},
                        evidence_index={}, manifest=manifest)
        loaded = json.loads((tmp_path / "llm_digest" / "generation_manifest.json").read_text())
        assert loaded["mode"] == "deterministic"
        assert loaded["llm_overlay"] is None

    def test_agent_md_handles_pos_as_list(self, tmp_path):
        """DigestRenderer must handle pos stored as [x, y] list (real engine format)."""
        renderer = DigestRenderer(tmp_path)
        agent_digest = _minimal_agent_digest()
        agent_digest["final_state"]["pos"] = [3, 7]  # list format as emitted by real engine
        renderer.render(_minimal_run_digest(),
                        agent_digests={"Ada": agent_digest},
                        evidence_index={}, manifest={})
        md = (tmp_path / "llm_digest" / "agents" / "Ada.md").read_text()
        assert "(3, 7)" in md
        assert "None" not in md
