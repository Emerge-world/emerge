from dataclasses import replace

import main as main_module
from simulation.runtime_profiles import build_default_profile


def test_main_builds_profile_and_passes_it_to_engine(monkeypatch):
    captured = {}

    class FakeEngine:
        def __init__(self, *, profile, run_digest, **kwargs):
            captured["profile"] = profile
            captured["run_digest"] = run_digest
            self.profile = profile
            self.run_id = "run-123"
            self.wandb_logger = None

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr(main_module, "SimulationEngine", FakeEngine)
    monkeypatch.setattr(main_module, "setup_logging", lambda verbose: None)
    monkeypatch.setattr(
        "sys.argv",
        ["main.py", "--agents", "2", "--ticks", "5", "--seed", "9", "--no-llm"],
    )

    main_module.main()

    assert captured["profile"].runtime.agents == 2
    assert captured["profile"].runtime.ticks == 5
    assert captured["profile"].runtime.seed == 9
    assert captured["profile"].runtime.use_llm is False
    assert captured["run_digest"] is True
    assert captured["ran"] is True


def test_main_passes_false_run_digest_when_no_digest_flag_is_set(monkeypatch):
    captured = {}

    class FakeEngine:
        def __init__(self, *, profile, run_digest, **kwargs):
            captured["run_digest"] = run_digest
            self.profile = profile
            self.run_id = "run-124"
            self.wandb_logger = None

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr(main_module, "SimulationEngine", FakeEngine)
    monkeypatch.setattr(main_module, "setup_logging", lambda verbose: None)
    monkeypatch.setattr(
        "sys.argv",
        ["main.py", "--ticks", "1", "--no-digest"],
    )

    main_module.main()

    assert captured["run_digest"] is False
    assert captured["ran"] is True


def test_main_derives_wandb_run_config_from_engine_profile(monkeypatch, tmp_path):
    captured = {}
    requested = build_default_profile()
    normalized = replace(
        requested,
        runtime=replace(requested.runtime, agents=11, use_llm=False),
    )

    class FakeEngine:
        def __init__(self, *, profile, **kwargs):
            self.profile = normalized
            self.run_id = "run-456"
            self.wandb_logger = None

        def run(self):
            captured["ran"] = True

    class FakeWandbLogger:
        def __init__(self, *, run_config, run_name, **kwargs):
            captured["run_config"] = run_config
            captured["run_name"] = run_name

    monkeypatch.setattr(main_module, "SimulationEngine", FakeEngine)
    monkeypatch.setattr(main_module, "WandbLogger", FakeWandbLogger)
    monkeypatch.setattr(main_module, "setup_logging", lambda verbose: None)
    monkeypatch.setattr(
        "sys.argv",
        ["main.py", "--wandb", "--wandb-run-name", "cli-name", "--ticks", "1"],
    )

    main_module.main()

    assert captured["run_config"]["profile/runtime/agents"] == 11
    assert captured["run_config"]["profile/runtime/use_llm"] is False
    assert captured["run_config"]["LLM_TEMPERATURE"] == main_module.sim_config.LLM_TEMPERATURE
    assert "agents" not in captured["run_config"]
    assert captured["run_name"] == "cli-name"
