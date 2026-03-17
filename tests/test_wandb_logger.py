"""Tests for WandbLogger — all wandb calls are mocked."""
import hashlib
import json
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
            (0, 1): {"type": "fruit", "quantity": 1},
            (1, 1): {"type": "stone", "quantity": 2},
        })
        oracle = self._make_oracle(precedent_count=7)
        tick_data = {"actions": [], "oracle_results": [],
                     "deaths": 0, "births": 0, "innovations": 0, "is_daytime": True}
        logger.log_tick(2, [self._make_agent()], world, oracle, tick_data)
        m = mock_wandb.log.call_args[0][0]
        assert m["world/resources/fruit"] == 4
        assert m["world/resources/stone"] == 2
        assert "world/total_resources" not in m
        assert m["oracle/precedent_count"] == 7
        assert m["sim/is_daytime"] == 1


class TestWandbLoggerRunName:
    """Tests for run_name parameter support."""

    def test_wandb_logger_passes_run_name_to_init(self, tmp_path):
        """WandbLogger should pass run_name to wandb.init as name=."""
        with patch("simulation.wandb_logger.wandb") as mock_wandb:
            mock_wandb.init.return_value = MagicMock()
            mock_wandb.Artifact.return_value = MagicMock()

            from simulation.wandb_logger import WandbLogger
            WandbLogger(
                project="test-proj",
                entity=None,
                run_config={},
                prompts_dir=tmp_path,
                run_name="my_run_01",
            )

            init_kwargs = mock_wandb.init.call_args.kwargs
            assert init_kwargs.get("name") == "my_run_01"

    def test_wandb_logger_no_run_name_defaults_to_none(self, tmp_path):
        """WandbLogger without run_name should not pass name= to wandb.init."""
        with patch("simulation.wandb_logger.wandb") as mock_wandb:
            mock_wandb.init.return_value = MagicMock()
            mock_wandb.Artifact.return_value = MagicMock()

            from simulation.wandb_logger import WandbLogger
            WandbLogger(
                project="test-proj",
                entity=None,
                run_config={},
                prompts_dir=tmp_path,
            )

            init_kwargs = mock_wandb.init.call_args.kwargs
            assert init_kwargs.get("name") is None


# ---------------------------------------------------------------------------
# Helpers for TestWandbLoggerPostRun
# ---------------------------------------------------------------------------

def _make_ebs_json(tmp_path: Path, ebs: float = 0.75, components: dict | None = None) -> Path:
    """Write a minimal metrics/ebs.json and return the run_dir."""
    run_dir = tmp_path / "run_001"
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True)
    data = {
        "ebs": ebs,
        "components": components or {
            "novelty":     {"score": 0.8, "sub_scores": {"approval_rate": 0.7, "uniqueness_rate": 0.9}},
            "utility":     {"score": 0.7, "sub_scores": {"survival_impact": 0.6}},
            "realization": {"score": 0.6, "sub_scores": {"completion_rate": 0.5}},
            "stability":   {"score": 0.9, "sub_scores": {"survival_rate": 0.95}},
            "autonomy":    {
                "score": 0.5,
                "sub_scores": {
                    "behavioral_initiative": 0.4,
                    "knowledge_accumulation": 0.6,
                    "planning_effectiveness": 0.5,
                },
                "detail": {"proactive_rate": 0.3, "reactive_rate": 0.7},
            },
            "longevity":   {"score": 0.65, "sub_scores": {"population_vitality": 0.7, "absolute_longevity": 0.6}},
        },
    }
    (metrics_dir / "ebs.json").write_text(json.dumps(data), encoding="utf-8")
    return run_dir


def _make_digest_json(run_dir: Path, agents: list | None = None, anomaly_counts: dict | None = None) -> None:
    """Write a minimal llm_digest/run_digest.json."""
    digest_dir = run_dir / "llm_digest"
    digest_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "outcomes": {
            "total_anomalies": 3,
            "total_innovations_approved": 2,
            "total_innovations_attempted": 4,
            "anomaly_counts_by_type": anomaly_counts or {"stuck": 2, "invalid_action": 1},
        },
        "agents": agents or [
            {
                "agent_id": "agent_0",
                "dominant_mode": "explore",
                "phase_count": 5,
                "anomaly_count": 1,
                "innovation_count": 2,
            }
        ],
    }
    (digest_dir / "run_digest.json").write_text(json.dumps(data), encoding="utf-8")


def _make_logger(mock_wandb, tmp_path: Path):
    """Instantiate WandbLogger with mocked wandb."""
    from simulation.wandb_logger import WandbLogger
    mock_wandb.Artifact.return_value = MagicMock()
    return WandbLogger(project="test", entity=None, run_config={}, prompts_dir=tmp_path)


def _collect_log_calls(mock_wandb) -> dict:
    """Aggregate all wandb.log call dicts into one flat dict."""
    return {k: v for call_ in mock_wandb.log.call_args_list for k, v in call_[0][0].items()}


class TestWandbLoggerPostRun:
    """Tests for WandbLogger.log_post_run()."""

    @patch("simulation.wandb_logger.wandb")
    def test_logs_ebs_score(self, mock_wandb, tmp_path):
        run_dir = _make_ebs_json(tmp_path, ebs=0.75)
        wl = _make_logger(mock_wandb, tmp_path)
        mock_wandb.log.reset_mock()
        wl.log_post_run(run_dir, include_digest=False)
        logged = _collect_log_calls(mock_wandb)
        assert logged["post_run/ebs"] == 0.75

    @patch("simulation.wandb_logger.wandb")
    def test_logs_all_six_ebs_components(self, mock_wandb, tmp_path):
        run_dir = _make_ebs_json(tmp_path)
        wl = _make_logger(mock_wandb, tmp_path)
        mock_wandb.log.reset_mock()
        wl.log_post_run(run_dir, include_digest=False)
        logged = _collect_log_calls(mock_wandb)
        for name in ("novelty", "utility", "realization", "stability", "autonomy", "longevity"):
            assert f"post_run/ebs_{name}" in logged

    @patch("simulation.wandb_logger.wandb")
    def test_logs_ebs_sub_scores(self, mock_wandb, tmp_path):
        run_dir = _make_ebs_json(tmp_path)
        wl = _make_logger(mock_wandb, tmp_path)
        mock_wandb.log.reset_mock()
        wl.log_post_run(run_dir, include_digest=False)
        logged = _collect_log_calls(mock_wandb)
        assert logged["post_run/ebs_novelty/approval_rate"] == pytest.approx(0.7)
        assert logged["post_run/ebs_longevity/population_vitality"] == pytest.approx(0.7)
        assert logged["post_run/ebs_longevity/absolute_longevity"] == pytest.approx(0.6)
        assert logged["post_run/ebs_autonomy/behavioral_initiative"] == pytest.approx(0.4)

    @patch("simulation.wandb_logger.wandb")
    def test_logs_ebs_detail_signals(self, mock_wandb, tmp_path):
        run_dir = _make_ebs_json(tmp_path)
        wl = _make_logger(mock_wandb, tmp_path)
        mock_wandb.log.reset_mock()
        wl.log_post_run(run_dir, include_digest=False)
        logged = _collect_log_calls(mock_wandb)
        assert logged["post_run/ebs_autonomy/detail/proactive_rate"] == pytest.approx(0.3)
        assert logged["post_run/ebs_autonomy/detail/reactive_rate"] == pytest.approx(0.7)

    @patch("simulation.wandb_logger.wandb")
    def test_logs_digest_summary_metrics(self, mock_wandb, tmp_path):
        run_dir = _make_ebs_json(tmp_path)
        _make_digest_json(run_dir)
        wl = _make_logger(mock_wandb, tmp_path)
        mock_wandb.log.reset_mock()
        wl.log_post_run(run_dir, include_digest=True)
        logged = _collect_log_calls(mock_wandb)
        assert logged["post_run/total_anomalies"] == 3
        assert logged["post_run/total_innovations_approved"] == 2
        assert logged["post_run/total_innovations_attempted"] == 4

    @patch("simulation.wandb_logger.wandb")
    def test_logs_per_agent_metrics(self, mock_wandb, tmp_path):
        run_dir = _make_ebs_json(tmp_path)
        _make_digest_json(run_dir)
        wl = _make_logger(mock_wandb, tmp_path)
        mock_wandb.log.reset_mock()
        wl.log_post_run(run_dir, include_digest=True)
        logged = _collect_log_calls(mock_wandb)
        assert logged["post_run/agent/agent_0/dominant_mode"] == "explore"
        assert logged["post_run/agent/agent_0/phase_count"] == 5
        assert logged["post_run/agent/agent_0/anomaly_count"] == 1
        assert logged["post_run/agent/agent_0/innovation_count"] == 2

    @patch("simulation.wandb_logger.wandb")
    def test_logs_anomaly_type_breakdown(self, mock_wandb, tmp_path):
        run_dir = _make_ebs_json(tmp_path)
        _make_digest_json(run_dir, anomaly_counts={"stuck": 2, "invalid_action": 1})
        wl = _make_logger(mock_wandb, tmp_path)
        mock_wandb.log.reset_mock()
        wl.log_post_run(run_dir, include_digest=True)
        logged = _collect_log_calls(mock_wandb)
        assert logged["post_run/anomaly_type/stuck"] == 2
        assert logged["post_run/anomaly_type/invalid_action"] == 1

    @patch("simulation.wandb_logger.wandb")
    def test_uploads_llm_digest_artifact(self, mock_wandb, tmp_path):
        run_dir = _make_ebs_json(tmp_path)
        _make_digest_json(run_dir)
        wl = _make_logger(mock_wandb, tmp_path)
        mock_artifact = MagicMock()
        mock_wandb.Artifact.return_value = mock_artifact
        mock_wandb.log.reset_mock()
        mock_wandb.Artifact.reset_mock()
        mock_wandb.log_artifact.reset_mock()
        wl.log_post_run(run_dir, include_digest=True)
        mock_wandb.Artifact.assert_called_once_with(
            name=f"{run_dir.name}-llm-digest", type="llm-digest"
        )
        mock_artifact.add_dir.assert_called_once()
        mock_wandb.log_artifact.assert_called_once_with(mock_artifact)

    @patch("simulation.wandb_logger.wandb")
    def test_skips_artifact_when_include_digest_false(self, mock_wandb, tmp_path):
        run_dir = _make_ebs_json(tmp_path)
        _make_digest_json(run_dir)
        mock_wandb.Artifact.return_value = MagicMock()
        wl = _make_logger(mock_wandb, tmp_path)
        mock_wandb.Artifact.reset_mock()
        wl.log_post_run(run_dir, include_digest=False)
        mock_wandb.Artifact.assert_not_called()

    @patch("simulation.wandb_logger.wandb")
    def test_missing_ebs_json_does_not_crash(self, mock_wandb, tmp_path):
        run_dir = tmp_path / "run_no_ebs"
        run_dir.mkdir()
        wl = _make_logger(mock_wandb, tmp_path)
        # Must not raise
        wl.log_post_run(run_dir, include_digest=False)

    @patch("simulation.wandb_logger.wandb")
    def test_missing_digest_json_does_not_crash(self, mock_wandb, tmp_path):
        run_dir = _make_ebs_json(tmp_path)
        # llm_digest dir not created
        wl = _make_logger(mock_wandb, tmp_path)
        wl.log_post_run(run_dir, include_digest=True)

    @patch("simulation.wandb_logger.wandb")
    def test_empty_llm_digest_dir_skips_artifact(self, mock_wandb, tmp_path):
        run_dir = _make_ebs_json(tmp_path)
        (run_dir / "llm_digest").mkdir(parents=True)
        mock_wandb.Artifact.return_value = MagicMock()
        wl = _make_logger(mock_wandb, tmp_path)
        mock_wandb.Artifact.reset_mock()
        wl.log_post_run(run_dir, include_digest=True)
        # Artifact should not be created for empty dir
        mock_wandb.Artifact.assert_not_called()
