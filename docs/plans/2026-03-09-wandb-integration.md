# W&B Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add optional Weights & Biases experiment tracking to the Emerge simulation via a `--wandb` CLI flag, logging per-tick aggregate metrics, run config, and versioned prompt artifacts.

**Architecture:** A new `WandbLogger` passive observer class (modeled after `AuditRecorder`) is wired into `SimulationEngine.__init__`. The engine calls `log_tick()` at the end of each tick and `finish()` at simulation end. If `--wandb` is not set, `wandb_logger=None` and all calls are skipped with zero performance impact.

**Tech Stack:** `wandb>=0.18`, `unittest.mock.patch` for tests, `statistics` stdlib for aggregates, `hashlib` for prompt hashing.

---

### Task 1: Install wandb dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add wandb to project dependencies**

Run: `uv add wandb`

Expected: pyproject.toml updated, wandb installed.

**Step 2: Verify installation**

Run: `uv run python -c "import wandb; print(wandb.__version__)"`

Expected: version string printed (e.g. `0.18.x`).

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add wandb dependency"
```

---

### Task 2: WandbLogger — skeleton with `__init__` and `finish`

**Files:**
- Create: `simulation/wandb_logger.py`
- Create: `tests/test_wandb_logger.py`

**Step 1: Write the failing test**

Create `tests/test_wandb_logger.py`:

```python
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
        # Keys look like "prompt/agent/system.txt" -> sha256 hash
        prompt_keys = [k for k in config_logged if k.startswith("prompt/")]
        assert len(prompt_keys) == 2
        # Verify the hash is correct
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
        # No prompt keys in config, no artifact uploaded
        config_logged = mock_wandb.init.call_args[1]["config"]
        assert not any(k.startswith("prompt/") for k in config_logged)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_wandb_logger.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'simulation.wandb_logger'`

**Step 3: Create `simulation/wandb_logger.py`**

```python
"""Weights & Biases experiment logger for Emerge simulation.

Passive observer: receives tick data from the engine and logs per-tick
aggregate metrics. Zero impact on the simulation when --wandb is not set.
"""
import hashlib
import statistics
from pathlib import Path
from typing import Optional

import wandb


class WandbLogger:
    """Logs per-tick aggregate metrics to Weights & Biases."""

    def __init__(
        self,
        project: str,
        entity: Optional[str],
        run_config: dict,
        prompts_dir: Path,
    ) -> None:
        prompt_hashes = self._hash_prompts(prompts_dir)
        config = {
            **run_config,
            **{f"prompt/{k}": v["sha256"] for k, v in prompt_hashes.items()},
        }
        wandb.init(project=project, entity=entity, config=config)
        if prompt_hashes:
            self._upload_prompt_artifact(prompts_dir, prompt_hashes)

    def _hash_prompts(self, prompts_dir: Path) -> dict[str, dict]:
        """Return {relative_path: {"sha256": ..., "text": ...}} for each .txt file."""
        result = {}
        if prompts_dir.exists():
            for txt_file in sorted(prompts_dir.rglob("*.txt")):
                key = str(txt_file.relative_to(prompts_dir))
                content = txt_file.read_text(encoding="utf-8")
                result[key] = {
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "text": content,
                }
        return result

    def _upload_prompt_artifact(self, prompts_dir: Path, prompt_hashes: dict) -> None:
        """Upload all prompt .txt files as a versioned W&B Artifact."""
        artifact = wandb.Artifact("emerge-prompts", type="prompt")
        for txt_file in sorted(prompts_dir.rglob("*.txt")):
            artifact.add_file(
                str(txt_file),
                name=str(txt_file.relative_to(prompts_dir)),
            )
        wandb.log_artifact(artifact)

    def log_tick(
        self,
        tick: int,
        alive_agents: list,
        world,
        oracle,
        tick_data: dict,
    ) -> None:
        """Compute per-tick aggregates and log to W&B."""
        # Filled in Task 3
        pass

    def finish(self) -> None:
        """Signal end of run to W&B."""
        wandb.finish()
```

**Step 4: Run tests to verify init/finish tests pass**

Run: `uv run pytest tests/test_wandb_logger.py::TestWandbLoggerInit -v`

Expected: all 6 tests PASS.

**Step 5: Commit**

```bash
git add simulation/wandb_logger.py tests/test_wandb_logger.py
git commit -m "feat(wandb): add WandbLogger skeleton with init and finish"
```

---

### Task 3: WandbLogger — `log_tick` method

**Files:**
- Modify: `simulation/wandb_logger.py`
- Modify: `tests/test_wandb_logger.py`

**Step 1: Write failing tests — add to `tests/test_wandb_logger.py`**

```python
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
        # resources: dict of pos -> {item: qty}
        world.resources = resources or {(0, 0): {"fruit": 3}, (1, 1): {"stone": 2}}
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
        world = self._make_world(resources={(0, 0): {"fruit": 3}, (1, 1): {"stone": 2}})
        oracle = self._make_oracle(precedent_count=7)
        tick_data = {"actions": [], "oracle_results": [],
                     "deaths": 0, "births": 0, "innovations": 0, "is_daytime": True}
        logger.log_tick(2, [self._make_agent()], world, oracle, tick_data)
        m = mock_wandb.log.call_args[0][0]
        assert m["world/total_resources"] == 5  # 3 + 2
        assert m["oracle/precedent_count"] == 7
        assert m["sim/is_daytime"] == 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_wandb_logger.py::TestWandbLoggerLogTick -v`

Expected: FAIL — `log_tick` is a no-op stub.

**Step 3: Implement `log_tick` in `simulation/wandb_logger.py`**

Replace the `log_tick` stub:

```python
    BASE_ACTION_TYPES = [
        "move", "eat", "rest", "innovate",
        "pickup", "give_item", "teach", "reproduce",
    ]

    def log_tick(
        self,
        tick: int,
        alive_agents: list,
        world,
        oracle,
        tick_data: dict,
    ) -> None:
        """Compute per-tick aggregates and log to W&B."""
        metrics: dict = {}

        # --- Agent aggregates ---
        metrics["agents/alive"] = len(alive_agents)
        if alive_agents:
            lives = [a.life for a in alive_agents]
            hungers = [a.hunger for a in alive_agents]
            energies = [a.energy for a in alive_agents]
            metrics["agents/mean_life"] = statistics.mean(lives)
            metrics["agents/min_life"] = min(lives)
            metrics["agents/max_life"] = max(lives)
            metrics["agents/mean_hunger"] = statistics.mean(hungers)
            metrics["agents/min_hunger"] = min(hungers)
            metrics["agents/max_hunger"] = max(hungers)
            metrics["agents/mean_energy"] = statistics.mean(energies)
            metrics["agents/min_energy"] = min(energies)
            metrics["agents/max_energy"] = max(energies)
        else:
            for stat in ("life", "hunger", "energy"):
                metrics[f"agents/mean_{stat}"] = 0
                metrics[f"agents/min_{stat}"] = 0
                metrics[f"agents/max_{stat}"] = 0

        metrics["agents/deaths_this_tick"] = tick_data.get("deaths", 0)
        metrics["agents/births_this_tick"] = tick_data.get("births", 0)

        # --- Actions ---
        actions = tick_data.get("actions", [])
        oracle_results = tick_data.get("oracle_results", [])
        metrics["actions/total"] = len(actions)
        metrics["actions/oracle_success_rate"] = (
            sum(oracle_results) / len(oracle_results) if oracle_results else 0.0
        )
        metrics["actions/innovations"] = tick_data.get("innovations", 0)
        for action_type in self.BASE_ACTION_TYPES:
            metrics[f"actions/by_type/{action_type}"] = sum(
                1 for a in actions if a == action_type
            )
        metrics["actions/by_type/other"] = sum(
            1 for a in actions if a not in self.BASE_ACTION_TYPES
        )

        # --- World ---
        metrics["world/total_resources"] = sum(
            sum(res.values()) for res in world.resources.values()
        )

        # --- Oracle ---
        metrics["oracle/precedent_count"] = len(oracle.precedents)

        # --- Day/night ---
        metrics["sim/is_daytime"] = 1 if tick_data.get("is_daytime", True) else 0

        wandb.log(metrics, step=tick)
```

**Step 4: Run all WandbLogger tests**

Run: `uv run pytest tests/test_wandb_logger.py -v`

Expected: all tests PASS.

**Step 5: Commit**

```bash
git add simulation/wandb_logger.py tests/test_wandb_logger.py
git commit -m "feat(wandb): implement log_tick with per-tick aggregate metrics"
```

---

### Task 4: Wire WandbLogger into SimulationEngine

**Files:**
- Modify: `simulation/engine.py`

**Step 1: No new tests needed** — integration is thin wiring code. Existing test suite verifies no regression.

Run the existing test suite first to establish baseline:

Run: `uv run pytest -m "not slow" -q`

Expected: all pass.

**Step 2: Add import and `wandb_logger` parameter to `__init__`**

At the top of `engine.py`, after the `AuditRecorder` import (line 22):

```python
from simulation.wandb_logger import WandbLogger
```

In `SimulationEngine.__init__` signature (line 33), add after `world_height`:

```python
        wandb_logger: Optional["WandbLogger"] = None,
```

After the `self.recorder` block (around line 108), add:

```python
        # W&B logger (optional)
        self.wandb_logger: Optional[WandbLogger] = wandb_logger
```

**Step 3: Accumulate `tick_data` in `_run_tick`**

At the **start** of `_run_tick` (line 139), after `time_description = ...`, add:

```python
        # Per-tick data for W&B logging
        tick_data: dict = {
            "actions": [],
            "oracle_results": [],
            "deaths": 0,
            "births": 0,
            "innovations": 0,
            "is_daytime": self.day_cycle.get_period(tick) == "day",
        }
```

After `self._tick_events.append({...})` (around line 220), add:

```python
            # Accumulate for W&B
            if self.wandb_logger:
                tick_data["actions"].append(action_str)
                tick_data["oracle_results"].append(result["success"])
```

After `self.agents.append(child)` / `alive_agents.append(child)` (line ~232), add:

```python
                if self.wandb_logger:
                    tick_data["births"] += 1
```

After `self.lineage.record_death(agent.name, tick)` (line ~255), add:

```python
                if self.wandb_logger:
                    tick_data["deaths"] += 1
```

After `self.lineage.record_innovation(agent.name, ...)` (line ~261), add:

```python
                if self.wandb_logger:
                    tick_data["innovations"] += 1
```

At the **end** of `_run_tick`, just before `self._print_agent_states()` (line ~302), add:

```python
        # Log tick to W&B
        if self.wandb_logger:
            self.wandb_logger.log_tick(
                tick, alive_agents, self.world, self.oracle, tick_data
            )
```

**Step 4: Call `finish()` in `run()`**

In the `run()` method, inside the `finally` block (after `self.lineage.save(...)`, around line 135), add:

```python
            if self.wandb_logger:
                self.wandb_logger.finish()
```

**Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest -m "not slow" -q`

Expected: all pass.

**Step 6: Smoke test without --wandb (unchanged behavior)**

Run: `uv run main.py --no-llm --ticks 3 --agents 1`

Expected: simulation runs normally, no W&B output.

**Step 7: Commit**

```bash
git add simulation/engine.py
git commit -m "feat(wandb): wire WandbLogger into SimulationEngine"
```

---

### Task 5: Add `--wandb` CLI flags to `main.py`

**Files:**
- Modify: `main.py`

**Step 1: Add imports to `main.py`**

After `from simulation.config import ...` (line 17), add:

```python
from pathlib import Path
from simulation.wandb_logger import WandbLogger
from simulation import config as sim_config
```

**Step 2: Add CLI arguments**

After the `--height` argument (line 43), add:

```python
    parser.add_argument("--wandb", action="store_true",
                        help="Enable Weights & Biases experiment logging")
    parser.add_argument("--wandb-project", default="emerge",
                        help="W&B project name (default: emerge)")
    parser.add_argument("--wandb-entity", default=None,
                        help="W&B entity/team (default: your W&B account)")
```

**Step 3: Build `WandbLogger` and pass to engine**

After `setup_logging(args.verbose)` (line 46), add:

```python
    wandb_logger = None
    if args.wandb:
        run_config = {
            "agents": args.agents,
            "ticks": args.ticks,
            "seed": args.seed,
            "no_llm": args.no_llm,
            "width": args.width,
            "height": args.height,
            "start_hour": args.start_hour,
            "LLM_MODEL": sim_config.OLLAMA_MODEL,
            "LLM_TEMPERATURE": sim_config.LLM_TEMPERATURE,
            "MOVE_ENERGY_COST": sim_config.ENERGY_COST_MOVE,
            "REST_ENERGY_GAIN": sim_config.ENERGY_RECOVERY_REST,
            "INNOVATE_ENERGY_COST": sim_config.ENERGY_COST_INNOVATE,
            "MAX_HUNGER": sim_config.AGENT_MAX_HUNGER,
            "HUNGER_DAMAGE": sim_config.HUNGER_DAMAGE_PER_TICK,
            "LIFE_MAX": sim_config.AGENT_MAX_LIFE,
            "ENERGY_MAX": sim_config.AGENT_MAX_ENERGY,
            "MEMORY_EPISODIC_MAX": sim_config.MEMORY_EPISODIC_MAX,
            "MEMORY_SEMANTIC_MAX": sim_config.MEMORY_SEMANTIC_MAX,
            "MEMORY_COMPRESSION_INTERVAL": sim_config.MEMORY_COMPRESSION_INTERVAL,
        }
        prompts_dir = Path(__file__).parent / "prompts"
        wandb_logger = WandbLogger(
            project=args.wandb_project,
            entity=args.wandb_entity,
            run_config=run_config,
            prompts_dir=prompts_dir,
        )
```

Update the `SimulationEngine(...)` call (line 50) to pass `wandb_logger`:

```python
    engine = SimulationEngine(
        num_agents=args.agents,
        world_seed=args.seed,
        use_llm=not args.no_llm,
        max_ticks=args.ticks,
        audit=args.audit,
        start_hour=args.start_hour,
        world_width=args.width,
        world_height=args.height,
        wandb_logger=wandb_logger,
    )
```

**Step 4: Run full test suite**

Run: `uv run pytest -m "not slow" -q`

Expected: all pass.

**Step 5: Smoke test no-llm without --wandb**

Run: `uv run main.py --no-llm --ticks 5 --agents 1`

Expected: runs cleanly, no W&B output.

**Step 6: Commit**

```bash
git add main.py
git commit -m "feat(wandb): add --wandb, --wandb-project, --wandb-entity CLI flags"
```

---

### Task 6: End-to-end verification (requires W&B login)

**Step 1: Login to W&B**

Run: `uv run wandb login`

Expected: browser opens or API key prompted.

**Step 2: Run simulation with W&B enabled**

Run: `uv run main.py --no-llm --ticks 10 --agents 2 --seed 42 --wandb`

Expected:
- `wandb: Run data is saved locally in wandb/` printed
- Simulation runs 10 ticks
- `wandb: Syncing run ...` at end
- Run appears in W&B dashboard at https://wandb.ai

**Step 3: Verify dashboard**

In W&B UI:
- Confirm run config contains `agents: 2`, `seed: 42`, `LLM_MODEL`, two `prompt/...` hash keys
- Confirm `agents/alive`, `agents/mean_life`, etc. show time-series charts
- Confirm `actions/by_type/move`, `eat`, etc. are logged
- Confirm `oracle/precedent_count` grows over ticks
- Confirm "emerge-prompts" artifact is listed under the run with all prompt .txt files

**Step 4: Run second time with same seed, compare runs**

Run: `uv run main.py --no-llm --ticks 10 --agents 2 --seed 42 --wandb`

Expected: two runs in W&B with identical configs, overlapping metric curves.

**Step 5: Update DECISION_LOG.md**

Add entry:
```markdown
## [2026-03-09] W&B Integration

Added Weights & Biases experiment tracking as an optional observer (`--wandb` flag).
WandbLogger passive observer logs per-tick aggregate metrics (life/hunger/energy,
action type breakdown, deaths/births, oracle precedent growth, resource totals).
Prompt templates are uploaded as versioned W&B Artifacts for prompt change tracking.
Pattern mirrors AuditRecorder: optional, zero-impact when not set.
```

**Step 6: Final commit**

```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md
git commit -m "docs: record W&B integration decision"
```

---

## Verification Checklist

- [ ] `uv run pytest tests/test_wandb_logger.py -v` — all tests pass
- [ ] `uv run pytest -m "not slow" -q` — full test suite passes
- [ ] `uv run main.py --no-llm --ticks 5 --agents 1` — unchanged behavior
- [ ] `uv run main.py --no-llm --ticks 10 --agents 2 --seed 42 --wandb` — W&B run created
- [ ] W&B dashboard shows: per-tick metric charts, run config with prompt hashes, prompt artifact
- [ ] Two runs with same seed show identical config in W&B comparison view
