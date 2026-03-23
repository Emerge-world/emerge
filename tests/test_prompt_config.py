"""Tests for PromptConfig: from_disk, roundtrip, variable extraction, validation."""

import json
import pytest
from pathlib import Path

from simulation.evolution.prompt_config import PromptConfig


class TestFromDisk:
    def test_from_disk_loads_agent_prompts(self):
        cfg = PromptConfig.from_disk()
        assert "system" in cfg.agent_prompts
        assert "decision" in cfg.agent_prompts
        assert len(cfg.agent_prompts["system"]) > 0

    def test_from_disk_loads_oracle_prompts(self):
        cfg = PromptConfig.from_disk()
        assert "physical_system" in cfg.oracle_prompts
        assert len(cfg.oracle_prompts["physical_system"]) > 0

    def test_from_disk_missing_file_is_skipped(self, tmp_path):
        # Only create one agent prompt file
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "system.txt").write_text("Hello $name", encoding="utf-8")
        oracle_dir = tmp_path / "oracle"
        oracle_dir.mkdir()

        cfg = PromptConfig.from_disk(prompts_dir=tmp_path)
        assert "system" in cfg.agent_prompts
        assert "decision" not in cfg.agent_prompts


class TestRoundtrip:
    def test_save_and_load(self, tmp_path):
        cfg = PromptConfig(
            agent_prompts={"system": "Hello $name", "decision": "Do $action"},
            oracle_prompts={"physical_system": "Physics text"},
            metadata={"generation": 1},
        )
        path = tmp_path / "prompts.json"
        cfg.save(path)
        loaded = PromptConfig.load(path)
        assert loaded.agent_prompts == cfg.agent_prompts
        assert loaded.oracle_prompts == cfg.oracle_prompts
        assert loaded.metadata == cfg.metadata

    def test_to_dict_from_dict(self):
        cfg = PromptConfig(
            agent_prompts={"system": "Hello"},
            oracle_prompts={"physical_system": "Physics"},
        )
        d = cfg.to_dict()
        restored = PromptConfig.from_dict(d)
        assert restored.agent_prompts == cfg.agent_prompts
        assert restored.oracle_prompts == cfg.oracle_prompts

    def test_from_dict_handles_missing_keys(self):
        cfg = PromptConfig.from_dict({})
        assert cfg.agent_prompts == {}
        assert cfg.oracle_prompts == {}
        assert cfg.metadata == {}


class TestToLoaderDict:
    def test_to_loader_dict_keys(self):
        cfg = PromptConfig(
            agent_prompts={"system": "s", "decision": "d"},
            oracle_prompts={"physical_system": "p"},
        )
        d = cfg.to_loader_dict()
        assert "agent/system" in d
        assert "agent/decision" in d
        assert "oracle/physical_system" in d
        assert d["agent/system"] == "s"


class TestExtractVariables:
    def test_extracts_dollar_variables(self):
        text = "Hello $name, your $action is $valid_123"
        vars_ = PromptConfig.extract_variables(text)
        assert "$name" in vars_
        assert "$action" in vars_
        assert "$valid_123" in vars_

    def test_extracts_braced_variables(self):
        text = "Hello ${name} and ${value}"
        vars_ = PromptConfig.extract_variables(text)
        assert "${name}" in vars_
        assert "${value}" in vars_

    def test_empty_text(self):
        assert PromptConfig.extract_variables("") == set()

    def test_no_variables(self):
        assert PromptConfig.extract_variables("plain text here") == set()


class TestValidateAgainst:
    def test_valid_config_returns_no_errors(self):
        from simulation.evolution.prompt_config import REQUIRED_VARIABLES
        # Use the real disk config as both reference and candidate
        cfg = PromptConfig.from_disk()
        errors = cfg.validate_against(cfg)
        assert errors == []

    def test_missing_variable_returns_error(self):
        # Reference has $name in agent/system; mutated removes it
        reference = PromptConfig(
            agent_prompts={"system": "Hello $name your $actions here $personality_description $custom_actions_section"},
            oracle_prompts={},
        )
        broken = PromptConfig(
            agent_prompts={"system": "Hello nobody, no template vars at all"},
            oracle_prompts={},
        )
        errors = broken.validate_against(reference)
        assert len(errors) > 0
        assert "agent/system" in errors[0]

    def test_oracle_prompts_not_validated_for_variables(self):
        # Oracle prompts have no required variables — mutations are always "valid"
        reference = PromptConfig(agent_prompts={}, oracle_prompts={"physical_system": "some text"})
        mutated = PromptConfig(agent_prompts={}, oracle_prompts={"physical_system": "changed text"})
        errors = mutated.validate_against(reference)
        assert errors == []
