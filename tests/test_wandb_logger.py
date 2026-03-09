"""Tests for WandbLogger — all wandb calls are mocked."""
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


@pytest.fixture
def prompts_dir(tmp_path):
    """Create a minimal prompts directory for testing."""
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "system.txt").write_text("You are an agent.")
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir()
    (oracle_dir / "physical_system.txt").write_text("You are the oracle.")
    return tmp_path


@pytest.fixture
def run_config():
    return {"agents": 2, "ticks": 10, "seed": 42, "no_llm": True,
            "width": 15, "height": 15, "start_hour": 6,
            "LLM_MODEL": "qwen3.5:4b", "LLM_TEMPERATURE": 0.7}


class TestWandbLoggerInit:
    @patch("simulation.wandb_logger.wandb")
    def test_calls_wandb_init(self, mock_wandb, prompts_dir, run_config):
        from simulation.wandb_logger import WandbLogger
        WandbLogger(project="test-project", entity=None,
                    run_config=run_config, prompts_dir=prompts_dir)
        mock_wandb.init.assert_called_once()
        kwargs = mock_wandb.init.call_args[1]
        assert kwargs["project"] == "test-project"
        assert kwargs["entity"] is None

    @patch("simulation.wandb_logger.wandb")
    def test_config_contains_run_config_keys(self, mock_wandb, prompts_dir, run_config):
        from simulation.wandb_logger import WandbLogger
        WandbLogger(project="test", entity=None,
                    run_config=run_config, prompts_dir=prompts_dir)
        config_logged = mock_wandb.init.call_args[1]["config"]
        assert config_logged["agents"] == 2
        assert config_logged["seed"] == 42

    @patch("simulation.wandb_logger.wandb")
    def test_config_contains_prompt_hashes(self, mock_wandb, prompts_dir, run_config):
        from simulation.wandb_logger import WandbLogger
        WandbLogger(project="test", entity=None,
                    run_config=run_config, prompts_dir=prompts_dir)
        config_logged = mock_wandb.init.call_args[1]["config"]
        prompt_keys = [k for k in config_logged if k.startswith("prompt/")]
        assert len(prompt_keys) == 2
        expected = hashlib.sha256(b"You are an agent.").hexdigest()
        assert config_logged["prompt/agent/system.txt"] == expected

    @patch("simulation.wandb_logger.wandb")
    def test_uploads_prompt_artifact(self, mock_wandb, prompts_dir, run_config):
        from simulation.wandb_logger import WandbLogger
        mock_artifact = MagicMock()
        mock_wandb.Artifact.return_value = mock_artifact
        WandbLogger(project="test", entity=None,
                    run_config=run_config, prompts_dir=prompts_dir)
        mock_wandb.Artifact.assert_called_once_with("emerge-prompts", type="prompt")
        mock_wandb.log_artifact.assert_called_once_with(mock_artifact)

    @patch("simulation.wandb_logger.wandb")
    def test_finish_calls_wandb_finish(self, mock_wandb, prompts_dir, run_config):
        from simulation.wandb_logger import WandbLogger
        logger = WandbLogger(project="test", entity=None,
                             run_config=run_config, prompts_dir=prompts_dir)
        logger.finish()
        mock_wandb.finish.assert_called_once()

    @patch("simulation.wandb_logger.wandb")
    def test_missing_prompts_dir_does_not_crash(self, mock_wandb, tmp_path, run_config):
        from simulation.wandb_logger import WandbLogger
        nonexistent = tmp_path / "does_not_exist"
        logger = WandbLogger(project="test", entity=None,
                             run_config=run_config, prompts_dir=nonexistent)
        config_logged = mock_wandb.init.call_args[1]["config"]
        assert not any(k.startswith("prompt/") for k in config_logged)
