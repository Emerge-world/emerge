"""Tests for run_batch.py experiment runner."""
import sys
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load():
    """Import run_batch module (reload each time to avoid state bleed)."""
    import importlib
    import run_batch
    importlib.reload(run_batch)
    return run_batch


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def test_validate_rejects_missing_name():
    rb = _load()
    with pytest.raises(SystemExit):
        rb.validate_experiments([{"agents": 3}])


def test_validate_rejects_unknown_key():
    rb = _load()
    with pytest.raises(SystemExit):
        rb.validate_experiments([{"name": "x", "unknown_key": 1}])


def test_validate_accepts_valid_experiment():
    rb = _load()
    # Should not raise
    rb.validate_experiments([{"name": "test", "agents": 3, "ticks": 50, "seed": 1}])


# ---------------------------------------------------------------------------
# Expansion
# ---------------------------------------------------------------------------

def test_expand_single_run_no_suffix():
    rb = _load()
    exps = [{"name": "foo", "agents": 3}]
    expanded = rb.expand_experiments(exps)
    assert len(expanded) == 1
    assert expanded[0]["name"] == "foo"


def test_expand_multiple_runs_adds_suffix():
    rb = _load()
    exps = [{"name": "foo", "agents": 3, "runs": 3}]
    expanded = rb.expand_experiments(exps)
    assert len(expanded) == 3
    assert [e["name"] for e in expanded] == ["foo_run1", "foo_run2", "foo_run3"]


def test_expand_strips_runs_key():
    rb = _load()
    exps = [{"name": "foo", "runs": 2}]
    expanded = rb.expand_experiments(exps)
    for e in expanded:
        assert "runs" not in e


# ---------------------------------------------------------------------------
# Command building
# ---------------------------------------------------------------------------

def test_build_command_basic():
    rb = _load()
    exp = {"name": "foo", "agents": 3, "ticks": 50, "seed": 42}
    cmd = rb.build_command(exp)
    assert cmd[:3] == ["uv", "run", "main.py"]
    assert "--agents" in cmd and "3" in cmd
    assert "--ticks" in cmd and "50" in cmd
    assert "--seed" in cmd and "42" in cmd


def test_build_command_wandb_true_adds_flags():
    rb = _load()
    exp = {"name": "my_run", "wandb": True}
    cmd = rb.build_command(exp)
    assert "--wandb" in cmd
    assert "--wandb-run-name" in cmd
    assert "my_run" in cmd


def test_build_command_wandb_false_omits_flags():
    rb = _load()
    exp = {"name": "my_run", "wandb": False}
    cmd = rb.build_command(exp)
    assert "--wandb" not in cmd
    assert "--wandb-run-name" not in cmd


def test_build_command_wandb_defaults_to_true():
    rb = _load()
    exp = {"name": "my_run"}
    cmd = rb.build_command(exp)
    assert "--wandb" in cmd


def test_build_command_no_llm():
    rb = _load()
    exp = {"name": "x", "no_llm": True}
    cmd = rb.build_command(exp)
    assert "--no-llm" in cmd


def test_build_command_no_llm_false_omitted():
    rb = _load()
    exp = {"name": "x", "no_llm": False}
    cmd = rb.build_command(exp)
    assert "--no-llm" not in cmd
