from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

from simulation.agent import Agent
from simulation.engine import SimulationEngine
from simulation.memory import Memory
from simulation.oracle import Oracle
from simulation.runtime_policy import MemoryRuntimeSettings
from simulation.runtime_profiles import build_default_profile
from simulation.schemas import AgentDecisionResponse, AgentPlanResponse, MemoryCompressionResponse


class FakeLLM:
    def __init__(self, *, decision_response=None, plan_response=None, memory_response=None):
        self.model = "fake-model"
        self.last_call = {}
        self._decision_response = decision_response or AgentDecisionResponse(
            action="move",
            direction="east",
            reason="exploring",
        )
        self._plan_response = plan_response or AgentPlanResponse(
            goal="stabilize food",
            goal_type="survival",
            subgoals=[],
            horizon="short",
            success_signals=[],
            abort_conditions=[],
            confidence=0.5,
            rationale_summary="keep moving",
        )
        self._memory_response = memory_response or MemoryCompressionResponse(learnings=["lesson"])
        self.generate_structured = MagicMock(side_effect=self._generate_structured)

    def is_available(self):
        return True

    def _generate_structured(self, prompt, schema, system_prompt="", temperature=None, max_tokens=None):
        self.last_call = {
            "system_prompt": system_prompt,
            "user_prompt": prompt,
            "raw_response": "",
        }
        if schema is AgentDecisionResponse:
            return self._decision_response
        if schema is AgentPlanResponse:
            return self._plan_response
        if schema is MemoryCompressionResponse:
            return self._memory_response
        raise AssertionError(f"Unexpected schema: {schema}")


def _patch_runtime_side_effects(monkeypatch):
    monkeypatch.setattr("simulation.engine.TICK_DELAY_SECONDS", 0)
    monkeypatch.setattr("simulation.engine.MetricsBuilder.build", lambda self: None)
    monkeypatch.setattr("simulation.engine.EBSBuilder.build", lambda self: None)


def _read_events(run_dir: Path) -> list[dict]:
    path = run_dir / "events.jsonl"
    return [line for line in path.read_text().splitlines() if line]


def _make_profile(
    *,
    agents: int = 1,
    ticks: int = 1,
    seed: int = 7,
    use_llm: bool = False,
    explicit_planning: bool = True,
    semantic_memory: bool = True,
    innovation: bool = True,
    item_reflection: bool = True,
    social: bool = True,
    teach: bool = True,
    reproduction: bool = True,
):
    profile = build_default_profile()
    return replace(
        profile,
        runtime=replace(
            profile.runtime,
            agents=agents,
            ticks=ticks,
            seed=seed,
            use_llm=use_llm,
        ),
        capabilities=replace(
            profile.capabilities,
            explicit_planning=explicit_planning,
            semantic_memory=semantic_memory,
            innovation=innovation,
            item_reflection=item_reflection,
            social=social,
            teach=teach,
            reproduction=reproduction,
        ),
        persistence=replace(profile.persistence, mode="none"),
    )


def _make_engine(monkeypatch, tmp_path, **profile_kwargs) -> SimulationEngine:
    monkeypatch.chdir(tmp_path)
    _patch_runtime_side_effects(monkeypatch)
    profile = _make_profile(**profile_kwargs)
    return SimulationEngine(profile=profile, run_digest=False)


def test_planning_off_skips_planner_and_emits_no_planning_events(tmp_path, monkeypatch):
    fake_llm = FakeLLM(
        decision_response=AgentDecisionResponse(
            action="none",
            reason="noop",
        )
    )
    monkeypatch.setattr("simulation.engine.LLMClient", lambda **kwargs: fake_llm)
    engine = _make_engine(
        monkeypatch,
        tmp_path,
        agents=1,
        ticks=1,
        use_llm=True,
        explicit_planning=False,
    )

    planner_plan = MagicMock(return_value=None)
    engine.agents[0].planner.plan = planner_plan

    engine.run()

    planner_plan.assert_not_called()
    events = _read_events(engine.event_emitter.run_dir)
    assert not any("plan_created" in line or "plan_updated" in line for line in events)


def test_semantic_memory_off_skips_compression_and_prompt_knowledge(tmp_path, monkeypatch):
    engine = _make_engine(
        monkeypatch,
        tmp_path,
        agents=1,
        ticks=1,
        semantic_memory=False,
    )
    memory = engine.agents[0].memory_system
    memory.add_episode("I saw fruit.")
    memory.add_knowledge("Fruit grows on trees.")
    fake_llm = FakeLLM(
        memory_response=MemoryCompressionResponse(learnings=["semantic lesson"])
    )

    assert memory.should_compress(10) is False
    assert memory.compress(llm=fake_llm, tick=10, agent_name=engine.agents[0].name) == []
    assert memory.semantic == []
    assert "KNOWLEDGE" not in memory.to_prompt()
    fake_llm.generate_structured.assert_not_called()


def test_innovation_off_blocks_forced_innovation(tmp_path, monkeypatch):
    engine = _make_engine(
        monkeypatch,
        tmp_path,
        agents=1,
        ticks=1,
        innovation=False,
    )
    agent = engine.agents[0]

    assert "innovate" not in agent.actions

    result = engine.oracle.resolve_action(
        agent,
        {"action": "innovate", "new_action_name": "fish", "description": "catch fish"},
        tick=1,
    )

    assert result["success"] is False
    assert "Unknown action" in result["message"]


def test_item_reflection_off_blocks_forced_manual_reflection(tmp_path, monkeypatch):
    engine = _make_engine(
        monkeypatch,
        tmp_path,
        agents=1,
        ticks=1,
        item_reflection=False,
    )
    agent = engine.agents[0]
    agent.inventory.add("fruit", 1)

    assert "reflect_item_uses" not in agent.actions

    result = engine.oracle.resolve_action(
        agent,
        {"action": "reflect_item_uses", "item": "fruit"},
        tick=1,
    )

    assert result["success"] is False
    assert "Unknown action" in result["message"]


def test_social_off_blocks_forced_social_actions(tmp_path, monkeypatch):
    engine = _make_engine(
        monkeypatch,
        tmp_path,
        agents=2,
        ticks=1,
        social=False,
    )
    sender, target = engine.agents[:2]
    engine.oracle.current_tick_agents = [sender, target]
    sender.inventory.add("fruit", 1)

    assert "communicate" not in sender.actions
    assert "give_item" not in sender.actions
    assert "teach" not in sender.actions

    communicate = engine.oracle.resolve_action(
        sender,
        {"action": "communicate", "target": target.name, "message": "hello"},
        tick=1,
    )
    give_item = engine.oracle.resolve_action(
        sender,
        {"action": "give_item", "target": target.name, "item": "fruit", "quantity": 1},
        tick=1,
    )

    assert communicate["success"] is False
    assert give_item["success"] is False
    assert "Unknown action" in communicate["message"]
    assert "Unknown action" in give_item["message"]


def test_teach_off_preserves_other_social_actions(tmp_path, monkeypatch):
    engine = _make_engine(
        monkeypatch,
        tmp_path,
        agents=2,
        ticks=1,
        teach=False,
    )
    teacher, learner = engine.agents[:2]
    engine.oracle.current_tick_agents = [teacher, learner]
    engine.oracle.precedents["innovation:fire_making"] = {"description": "make fire"}

    assert "communicate" in teacher.actions
    assert "give_item" in teacher.actions
    assert "teach" not in teacher.actions

    result = engine.oracle.resolve_action(
        teacher,
        {"action": "teach", "target": learner.name, "skill": "fire_making"},
        tick=1,
    )

    assert result["success"] is False
    assert "Unknown action" in result["message"]


def test_reproduction_off_never_unlocks_or_spawns_child(tmp_path, monkeypatch):
    engine = _make_engine(
        monkeypatch,
        tmp_path,
        agents=2,
        ticks=1,
        reproduction=False,
    )
    ada, bruno = engine.agents[:2]
    engine.oracle.current_tick_agents = [ada, bruno]
    ada.x, ada.y = 0, 0
    bruno.x, bruno.y = 1, 0

    ada.unlock_actions_for_tick(10_000)

    assert "reproduce" not in ada.actions

    result = engine.oracle.resolve_action(
        ada,
        {"action": "reproduce", "target": bruno.name},
        tick=1,
    )

    assert result["success"] is False
    assert "Unknown action" in result["message"]
    assert "child_spawn" not in result
