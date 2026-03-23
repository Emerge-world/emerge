"""
Loads prompt templates from the prompts/ directory.
Templates use Python's string.Template syntax ($variable or ${variable}).

Override mechanism: call set_override(dict) to inject custom prompt texts
for a single execution context (e.g. during evolution runs). The override
is stored in a contextvars.ContextVar so it is isolated per-thread/task.
"""

import contextvars
from string import Template
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_cache: dict[str, str] = {}

# Per-context override: maps prompt name (e.g. "agent/system") → text
_prompt_override: contextvars.ContextVar[dict[str, str] | None] = (
    contextvars.ContextVar("_prompt_override", default=None)
)


def set_override(prompts: dict[str, str] | None) -> None:
    """
    Set (or clear) a per-context prompt override dict.

    Call with None to restore normal disk-based loading.
    """
    _prompt_override.set(prompts)


def load(name: str) -> str:
    """Load raw template text (e.g. 'agent/system').

    If a context override is active and contains this name, returns that
    text without touching the disk cache.
    """
    override = _prompt_override.get()
    if override is not None and name in override:
        return override[name]
    if name not in _cache:
        _cache[name] = (PROMPTS_DIR / f"{name}.txt").read_text()
    return _cache[name]


def render(template: str, **kwargs) -> str:
    """Load and render a template with $variable substitution."""
    return Template(load(template)).substitute(**kwargs)
