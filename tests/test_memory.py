"""
Tests for the dual memory system (episodic + semantic).
"""

from unittest.mock import MagicMock

import pytest

from simulation.memory import Memory
from simulation.config import (
    MEMORY_EPISODIC_MAX,
    MEMORY_SEMANTIC_MAX,
    MEMORY_COMPRESSION_INTERVAL,
)


# ------------------------------------------------------------------
# Episodic memory
# ------------------------------------------------------------------

class TestEpisodicMemory:
    def test_add_episode(self):
        mem = Memory()
        mem.add_episode("I moved east.")
        assert len(mem.episodic) == 1
        assert mem.episodic[0] == "I moved east."

    def test_episodic_cap(self):
        mem = Memory()
        for i in range(MEMORY_EPISODIC_MAX + 5):
            mem.add_episode(f"event {i}")
        assert len(mem.episodic) == MEMORY_EPISODIC_MAX

    def test_episodic_fifo_order(self):
        mem = Memory()
        for i in range(MEMORY_EPISODIC_MAX + 5):
            mem.add_episode(f"event {i}")
        # Oldest entries should be dropped
        assert mem.episodic[0] == "event 5"
        assert mem.episodic[-1] == f"event {MEMORY_EPISODIC_MAX + 4}"


# ------------------------------------------------------------------
# Semantic memory
# ------------------------------------------------------------------

class TestSemanticMemory:
    def test_add_knowledge(self):
        mem = Memory()
        mem.add_knowledge("Eating fruit reduces hunger.")
        assert len(mem.semantic) == 1
        assert mem.semantic[0] == "Eating fruit reduces hunger."

    def test_semantic_cap(self):
        mem = Memory()
        for i in range(MEMORY_SEMANTIC_MAX + 5):
            mem.add_knowledge(f"knowledge {i}")
        assert len(mem.semantic) == MEMORY_SEMANTIC_MAX

    def test_semantic_fifo_order(self):
        mem = Memory()
        for i in range(MEMORY_SEMANTIC_MAX + 3):
            mem.add_knowledge(f"knowledge {i}")
        assert mem.semantic[0] == "knowledge 3"
        assert mem.semantic[-1] == f"knowledge {MEMORY_SEMANTIC_MAX + 2}"


# ------------------------------------------------------------------
# Compression logic
# ------------------------------------------------------------------

class TestCompression:
    def test_should_compress_at_interval(self):
        mem = Memory()
        mem.add_episode("something happened")
        assert mem.should_compress(MEMORY_COMPRESSION_INTERVAL) is True

    def test_should_not_compress_before_interval(self):
        mem = Memory()
        mem.add_episode("something happened")
        assert mem.should_compress(MEMORY_COMPRESSION_INTERVAL - 1) is False

    def test_should_not_compress_without_episodes(self):
        mem = Memory()
        assert mem.should_compress(MEMORY_COMPRESSION_INTERVAL) is False

    def test_should_not_compress_at_non_multiple(self):
        mem = Memory()
        mem.add_episode("something happened")
        assert mem.should_compress(MEMORY_COMPRESSION_INTERVAL + 3) is False

    def test_should_not_compress_same_tick_twice(self):
        mem = Memory()
        mem.add_episode("something happened")
        tick = MEMORY_COMPRESSION_INTERVAL
        assert mem.should_compress(tick) is True
        mem.compress(llm=None, tick=tick, agent_name="Ada")
        assert mem.should_compress(tick) is False

    def test_compress_with_mock_llm(self):
        mem = Memory()
        for i in range(5):
            mem.add_episode(f"I moved to position {i}")

        mock_llm = MagicMock()
        typed = MagicMock()
        typed.learnings = ["Moving explores new areas", "Each move costs energy"]
        mock_llm.generate_structured.return_value = typed

        mem.compress(llm=mock_llm, tick=10, agent_name="Ada")
        assert len(mem.semantic) == 2
        assert "Moving explores new areas" in mem.semantic
        assert "Each move costs energy" in mem.semantic

    def test_compress_invalid_response(self):
        mem = Memory()
        mem.add_episode("something happened")

        mock_llm = MagicMock()
        mock_llm.generate_json.return_value = {"wrong_key": "bad data"}

        mem.compress(llm=mock_llm, tick=10, agent_name="Ada")
        # Should not crash, semantic stays empty
        assert len(mem.semantic) == 0

    def test_compress_none_response(self):
        mem = Memory()
        mem.add_episode("something happened")

        mock_llm = MagicMock()
        mock_llm.generate_json.return_value = None

        mem.compress(llm=mock_llm, tick=10, agent_name="Ada")
        assert len(mem.semantic) == 0

    def test_compress_llm_exception(self):
        mem = Memory()
        mem.add_episode("something happened")

        mock_llm = MagicMock()
        mock_llm.generate_json.side_effect = RuntimeError("LLM failed")

        mem.compress(llm=mock_llm, tick=10, agent_name="Ada")
        # Should not crash, semantic stays empty
        assert len(mem.semantic) == 0

    def test_compress_no_llm(self):
        mem = Memory()
        mem.add_episode("something happened")

        mem.compress(llm=None, tick=10, agent_name="Ada")
        assert len(mem.semantic) == 0
        # Should still mark tick as compressed
        assert mem._last_compression_tick == 10

    def test_compress_filters_empty_learnings(self):
        mem = Memory()
        mem.add_episode("something")

        mock_llm = MagicMock()
        typed = MagicMock()
        typed.learnings = ["valid lesson", "", "  ", "another lesson"]
        mock_llm.generate_structured.return_value = typed

        mem.compress(llm=mock_llm, tick=10, agent_name="Ada")
        assert len(mem.semantic) == 2
        assert "valid lesson" in mem.semantic
        assert "another lesson" in mem.semantic


# ------------------------------------------------------------------
# to_prompt formatting
# ------------------------------------------------------------------

class TestToPrompt:
    def test_empty_memory(self):
        mem = Memory()
        result = mem.to_prompt()
        assert "no previous memories" in result.lower()

    def test_episodes_only(self):
        mem = Memory()
        mem.add_episode("I moved east.")
        mem.add_episode("I ate fruit.")
        result = mem.to_prompt()
        assert "[RECENT]" in result
        assert "I moved east." in result
        assert "I ate fruit." in result
        assert "KNOWLEDGE" not in result

    def test_both_stores(self):
        mem = Memory()
        mem.add_knowledge("Fruit reduces hunger.")
        mem.add_episode("I moved east.")
        result = mem.to_prompt()
        assert "[KNOW]" in result
        assert "[RECENT]" in result
        assert "Fruit reduces hunger." in result
        assert "I moved east." in result

    def test_knowledge_before_episodes(self):
        mem = Memory()
        mem.add_knowledge("lesson")
        mem.add_episode("event")
        result = mem.to_prompt()
        know_pos = result.index("KNOWLEDGE")
        recent_pos = result.index("RECENT EVENTS")
        assert know_pos < recent_pos

    def test_knowledge_only(self):
        mem = Memory()
        mem.add_knowledge("Fruit reduces hunger.")
        result = mem.to_prompt()
        assert "[KNOW]" in result
        assert "RECENT EVENTS" not in result


# ------------------------------------------------------------------
# Backward compatibility
# ------------------------------------------------------------------

class TestBackwardCompat:
    def test_total_entries(self):
        mem = Memory()
        mem.add_episode("ep1")
        mem.add_episode("ep2")
        mem.add_knowledge("k1")
        assert mem.total_entries == 3

    def test_all_entries(self):
        mem = Memory()
        mem.add_episode("ep1")
        mem.add_knowledge("k1")
        entries = mem.all_entries()
        assert isinstance(entries, list)
        assert len(entries) == 2
        # Semantic first, then episodic
        assert entries[0] == "k1"
        assert entries[1] == "ep1"

    def test_all_entries_returns_copy(self):
        mem = Memory()
        mem.add_episode("ep1")
        entries = mem.all_entries()
        entries.append("should not appear")
        assert len(mem.episodic) == 1


class TestTaskMemory:
    def test_task_memory_cap(self):
        mem = Memory()

        for i in range(20):
            mem.add_task_entry(tick=i, kind="plan_result", summary=f"entry {i}")

        assert len(mem.task) == 12
        assert mem.task[0].summary == "entry 8"
