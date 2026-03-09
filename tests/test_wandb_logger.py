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


class TestWandbLoggerLogTick:
    """Tests for log_tick metric computation."""

    def _make_agent(self, life=80, hunger=30, energy=60):
        agent = MagicMock()
        agent.life = life
        agent.hunger = hunger
        agent.energy = energy
        return agent

    def _make_world(self, resources=None):
        world = MagicMock()
        # Match real World.resources structure: {"type": ..., "quantity": ...}
        world.resources = resources or {
            (0, 0): {"type": "fruit", "quantity": 3},
            (1, 1): {"type": "stone", "quantity": 2},
        }
        return world

    def _make_oracle(self, precedent_count=5):
        oracle = MagicMock()
        oracle.precedents = {str(i): {} for i in range(precedent_count)}
        return oracle

    @patch("simulation.wandb_logger.wandb")
    def test_log_tick_calls_wandb_log(self, mock_wandb, prompts_dir, run_config):
        from simulation.wandb_logger import WandbLogger
        logger = WandbLogger("test", None, run_config, prompts_dir)
        agents = [self._make_agent()]
        tick_data = {"actions": ["eat"], "oracle_results": [True],
                     "deaths": 0, "births": 0, "innovations": 0, "is_daytime": True}
        logger.log_tick(1, agents, self._make_world(), self._make_oracle(), tick_data)
        mock_wandb.log.assert_called_once()
        metrics, kwargs = mock_wandb.log.call_args[0][0], mock_wandb.log.call_args[1]
        assert kwargs.get("step") == 1

    @patch("simulation.wandb_logger.wandb")
    def test_agent_aggregates_correct(self, mock_wandb, prompts_dir, run_config):
        from simulation.wandb_logger import WandbLogger
        logger = WandbLogger("test", None, run_config, prompts_dir)
        agents = [
            self._make_agent(life=100, hunger=10, energy=90),
            self._make_agent(life=60,  hunger=50, energy=40),
        ]
        tick_data = {"actions": [], "oracle_results": [],
                     "deaths": 0, "births": 0, "innovations": 0, "is_daytime": True}
        logger.log_tick(1, agents, self._make_world(), self._make_oracle(), tick_data)
        m = mock_wandb.log.call_args[0][0]
        assert m["agents/alive"] == 2
        assert m["agents/mean_life"] == 80.0
        assert m["agents/min_life"] == 60
        assert m["agents/max_life"] == 100
        assert m["agents/mean_hunger"] == 30.0
        assert m["agents/mean_energy"] == 65.0

    @patch("simulation.wandb_logger.wandb")
    def test_zero_agents_does_not_crash(self, mock_wandb, prompts_dir, run_config):
        from simulation.wandb_logger import WandbLogger
        logger = WandbLogger("test", None, run_config, prompts_dir)
        tick_data = {"actions": [], "oracle_results": [],
                     "deaths": 2, "births": 0, "innovations": 0, "is_daytime": False}
        logger.log_tick(5, [], self._make_world(), self._make_oracle(), tick_data)
        m = mock_wandb.log.call_args[0][0]
        assert m["agents/alive"] == 0
        assert m["agents/mean_life"] == 0
        assert m["agents/deaths_this_tick"] == 2
        assert m["sim/is_daytime"] == 0

    @patch("simulation.wandb_logger.wandb")
    def test_action_metrics(self, mock_wandb, prompts_dir, run_config):
        from simulation.wandb_logger import WandbLogger
        logger = WandbLogger("test", None, run_config, prompts_dir)
        tick_data = {
            "actions": ["move", "eat", "move", "custom_dance"],
            "oracle_results": [True, True, False, True],
            "deaths": 0, "births": 1, "innovations": 1, "is_daytime": True,
        }
        logger.log_tick(3, [self._make_agent()], self._make_world(),
                        self._make_oracle(), tick_data)
        m = mock_wandb.log.call_args[0][0]
        assert m["actions/total"] == 4
        assert m["actions/oracle_success_rate"] == pytest.approx(0.75)
        assert m["actions/by_type/move"] == 2
        assert m["actions/by_type/eat"] == 1
        assert m["actions/by_type/other"] == 1  # custom_dance
        assert m["agents/births_this_tick"] == 1
        assert m["actions/innovations"] == 1

    @patch("simulation.wandb_logger.wandb")
    def test_world_and_oracle_metrics(self, mock_wandb, prompts_dir, run_config):
        from simulation.wandb_logger import WandbLogger
        logger = WandbLogger("test", None, run_config, prompts_dir)
        world = self._make_world(resources={
            (0, 0): {"type": "fruit", "quantity": 3},
            (1, 1): {"type": "stone", "quantity": 2},
        })
        oracle = self._make_oracle(precedent_count=7)
        tick_data = {"actions": [], "oracle_results": [],
                     "deaths": 0, "births": 0, "innovations": 0, "is_daytime": True}
        logger.log_tick(2, [self._make_agent()], world, oracle, tick_data)
        m = mock_wandb.log.call_args[0][0]
        assert m["world/total_resources"] == 5  # 3 + 2
        assert m["oracle/precedent_count"] == 7
        assert m["sim/is_daytime"] == 1
