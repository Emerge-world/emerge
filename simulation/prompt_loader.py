"""
Loads prompt templates from the prompts/ directory.
Templates use Python's string.Template syntax ($variable or ${variable}).
"""

from string import Template
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_cache: dict[str, str] = {}


def load(name: str) -> str:
    """Load raw template text (e.g. 'agent/system')."""
    if name not in _cache:
        _cache[name] = (PROMPTS_DIR / f"{name}.txt").read_text()
    return _cache[name]


def render(template: str, **kwargs) -> str:
    """Load and render a template with $variable substitution."""
    return Template(load(template)).substitute(**kwargs)
