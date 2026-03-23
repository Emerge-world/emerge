"""Tests for prompt_loader contextvars override mechanism."""

import pytest
import simulation.prompt_loader as prompt_loader


class TestPromptLoaderOverride:
    def test_override_returns_custom_text(self):
        custom = {"agent/system": "custom system prompt"}
        prompt_loader.set_override(custom)
        try:
            result = prompt_loader.load("agent/system")
            assert result == "custom system prompt"
        finally:
            prompt_loader.set_override(None)

    def test_override_does_not_affect_other_prompts(self):
        custom = {"agent/system": "custom system prompt"}
        prompt_loader.set_override(custom)
        try:
            # agent/decision is NOT in the override dict — should load from disk
            result = prompt_loader.load("agent/decision")
            assert "custom system prompt" not in result
            assert len(result) > 0  # real prompt loaded from disk
        finally:
            prompt_loader.set_override(None)

    def test_clear_override_restores_disk_loading(self):
        real = prompt_loader.load("agent/system")

        prompt_loader.set_override({"agent/system": "OVERRIDDEN"})
        assert prompt_loader.load("agent/system") == "OVERRIDDEN"

        prompt_loader.set_override(None)
        assert prompt_loader.load("agent/system") == real

    def test_none_override_uses_cache(self):
        # Ensure no override is active
        prompt_loader.set_override(None)
        result = prompt_loader.load("agent/system")
        assert len(result) > 0  # loaded from disk / cache

    def test_render_uses_override(self):
        custom = {"agent/system": "Hello $name end"}
        prompt_loader.set_override(custom)
        try:
            rendered = prompt_loader.render("agent/system", name="World",
                                            actions="", personality_description="",
                                            custom_actions_section="")
            assert "Hello World end" in rendered
        finally:
            prompt_loader.set_override(None)
