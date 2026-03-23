"""
Simulation engine: orchestrates the main tick loop.
"""

import time
import json
import logging
import threading
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Optional, Callable

from simulation.config import (
    MAX_AGENTS, MAX_TICKS, TICK_DELAY_SECONDS,
    AGENT_VISION_RADIUS, WORLD_WIDTH, WORLD_HEIGHT, WORLD_START_HOUR,
    AGENT_NAME_POOL, CHILD_START_LIFE, CHILD_START_HUNGER, CHILD_START_ENERGY,
    BONDING_TRUST_THRESHOLD, BASE_ACTIONS,
)
from simulation.world import World
from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.llm_client import LLMClient
from simulation.sim_logger import SimLogger
from simulation.event_emitter import EventEmitter
from simulation.wandb_logger import WandbLogger
from simulation.day_cycle import DayCycle
from simulation.lineage import LineageTracker
from simulation.personality import Personality
from simulation.metrics_builder import MetricsBuilder
from simulation.ebs_builder import EBSBuilder
from simulation.tick_limits import format_tick_limit, iter_tick_numbers
from simulation.subgoal_evaluator import check_completion, check_failure

logger = logging.getLogger(__name__)

_BASE_ACTIONS: frozenset[str] = frozenset(BASE_ACTIONS)


class SimulationEngine:
    """Main simulation engine."""

    def __init__(
        self,
        num_agents: int = 3,
        world_seed: Optional[int] = None,
        use_llm: bool = True,
        max_ticks: int | None = MAX_TICKS,
        start_hour: int = WORLD_START_HOUR,
        world_width: int = WORLD_WIDTH,
        world_height: int = WORLD_HEIGHT,
        wandb_logger: Optional["WandbLogger"] = None,
        ollama_model: Optional[str] = None,
        run_digest: bool = True,
    ):
        self.max_ticks = max_ticks
        self.current_tick = 0
        self.use_llm = use_llm
        self._world_seed = world_seed
        seed_str = str(world_seed) if world_seed is not None else "unseeded"
        self._precedents_path = f"data/precedents_{seed_str}.json"

        # Initialize LLM
        self.llm: Optional[LLMClient] = None
        if use_llm:
            kwargs = {"model": ollama_model} if ollama_model else {}
            self.llm = LLMClient(**kwargs)
            if not self.llm.is_available():
                logger.warning("⚠️  Ollama is not available. Running in fallback mode (no LLM).")
                self.llm = None
                self.use_llm = False

        # Day/night cycle
        self.day_cycle = DayCycle(start_hour=start_hour)

        # Create world
        self.world = World(width=world_width, height=world_height, seed=world_seed)

        # Create simulation logger
        self.sim_logger = SimLogger()

        # Create oracle
        self.oracle = Oracle(self.world, llm=self.llm, sim_logger=self.sim_logger,
                             day_cycle=self.day_cycle)

        # Auto-load precedents from previous runs
        self.oracle.load_precedents(self._precedents_path)

        # Lineage tracking
        seed_str = str(world_seed) if world_seed is not None else "unseeded"
        self._lineage_path = f"data/lineage_{seed_str}.json"
        self.lineage = LineageTracker()
        self.lineage.load(self._lineage_path)

        # Name pool management (tracks which names are in use)
        self._used_names: set[str] = set()

        # Create agents
        num_agents = min(num_agents, MAX_AGENTS)
        self.agents: list[Agent] = []
        for i in range(num_agents):
            x, y = self.world.find_spawn_point()
            agent = Agent(x=x, y=y, llm=self.llm)
            self.agents.append(agent)
            self._used_names.add(agent.name)
            self.lineage.record_birth(agent.name, [], 0, tick=0)

        # Web server: per-tick event collector (populated by run_with_callback)
        self._tick_events: list[dict] = []

        # Always-on canonical event emitter (data/runs/<run_id>/)
        _ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        _seed_part = f"s{world_seed}" if world_seed is not None else "unseeded"
        _short_uuid = uuid.uuid4().hex[:8]
        self.run_id = f"{_ts}_{_seed_part}_a{len(self.agents)}_{_short_uuid}"
        _agent_model_id = self.llm.model if self.llm else "none"
        _oracle_model_id = self.oracle.llm.model if self.oracle.llm else "none"
        self.event_emitter = EventEmitter(
            run_id=self.run_id,
            seed=world_seed,
            world_width=world_width,
            world_height=world_height,
            max_ticks=max_ticks,
            agent_count=len(self.agents),
            agent_names=[a.name for a in self.agents],
            agent_model_id=_agent_model_id,
            oracle_model_id=_oracle_model_id,
            day_cycle=self.day_cycle,
            precedents_file=self._precedents_path,
        )

        # W&B logger (optional)
        self.wandb_logger: Optional[WandbLogger] = wandb_logger
        self.run_digest = run_digest

        logger.info(f"Simulation initialized: {num_agents} agents, world {world_width}x{world_height}")

    @staticmethod
    def _agent_profile(agent) -> dict:
        return {
            "name": agent.name,
            "personality": asdict(agent.personality),
        }

    def run(self):
        """Run the complete simulation."""
        self._print_header()
        self._log_overview_start()
        self.event_emitter.emit_run_start(
            agent_names=[a.name for a in self.agents],
            model_id=self.llm.model if self.llm else "none",
            world_seed=self._world_seed,
            width=self.world.width,
            height=self.world.height,
            max_ticks=self.max_ticks,
            agent_profiles=[self._agent_profile(a) for a in self.agents],
        )

        try:
            for tick in iter_tick_numbers(self.max_ticks):
                alive_agents = [a for a in self.agents if a.alive]

                if not alive_agents:
                    self._print_separator()
                    print("\n☠️  ALL AGENTS HAVE DIED. End of simulation.")
                    break

                self.current_tick = tick
                self._run_tick(tick, alive_agents)

                if TICK_DELAY_SECONDS > 0:
                    time.sleep(TICK_DELAY_SECONDS)
        finally:
            self.oracle.save_precedents(
                self._precedents_path, self.current_tick, self._world_seed
            )
            self.lineage.save(self._lineage_path)
            survivors = [a.name for a in self.agents if a.alive]
            self.event_emitter.emit_run_end(self.current_tick, survivors, self.current_tick)
            self.event_emitter.close()
            try:
                MetricsBuilder(self.event_emitter.run_dir).build()
                EBSBuilder(self.event_emitter.run_dir).build()
            except Exception as exc:
                logger.warning("MetricsBuilder/EBSBuilder failed: %s", exc)
            if self.run_digest:
                try:
                    from simulation.digest.digest_builder import DigestBuilder
                    DigestBuilder(self.event_emitter.run_dir).build()
                except Exception as exc:
                    logger.warning("DigestBuilder failed: %s", exc)
            if self.wandb_logger:
                try:
                    self.wandb_logger.log_post_run(
                        self.event_emitter.run_dir,
                        include_digest=self.run_digest,
                    )
                except Exception as exc:
                    logger.warning("W&B post-run log failed: %s", exc)
                self.wandb_logger.finish()

        self._print_summary()

    def _run_tick(self, tick: int, alive_agents: list[Agent]):
        """Execute a complete tick."""
        vision_radius = self.day_cycle.get_vision_radius(tick)
        time_description = self.day_cycle.get_prompt_line(tick)

        # Per-tick data for W&B logging
        tick_data: dict = {
            "actions": [],
            "oracle_results": [],
            "deaths": 0,
            "births": 0,
            "innovations": 0,
            "is_daytime": self.day_cycle.get_period(tick) == "day",
        }

        self._print_tick_header(tick, alive_agents, time_description)
        self.sim_logger.log_tick_start(tick, alive_agents)

        # Snapshot world resources before any agent acts this tick
        resources_before = {pos: dict(res) for pos, res in self.world.resources.items()}

        # Reset per-tick Oracle state for communication
        self.oracle.current_tick_agents = alive_agents
        self.oracle._communicated_this_tick = set()

        for agent in alive_agents:
            if not agent.alive:
                continue

            agent.unlock_actions_for_tick(tick)

            # 1. Get environment perception (radius varies by time of day)
            nearby = self.world.get_nearby_tiles(agent.x, agent.y, vision_radius)

            # Gather nearby agents for social perception (same vision radius)
            nearby_agent_list = self.world.get_agents_in_radius(
                agent, alive_agents, vision_radius
            )

            # Snapshot inventory before oracle resolves the action
            inventory_before = dict(agent.inventory.items)

            # Emit perception snapshot before decision (used by EBSBuilder for Autonomy)
            resources_nearby = [
                {"type": t["resource"], "tile": t.get("type", ""), "dx": t["x"] - agent.x, "dy": t["y"] - agent.y}
                for t in nearby
                if t.get("resource")
            ]
            self.event_emitter.emit_agent_perception(
                tick, agent.name,
                pos={"x": agent.x, "y": agent.y},
                hunger=agent.hunger,
                energy=agent.energy,
                life=agent.life,
                resources_nearby=resources_nearby,
            )

            # 2. Agent decides its action
            action = agent.decide_action(nearby, tick, time_description,
                                         nearby_agents=nearby_agent_list,
                                         all_agents=alive_agents)
            action_str = action.get("action", "none")
            reason = action.get("reason", "")

            # Clear incoming messages now that agent has decided (consumed this tick)
            agent.incoming_messages.clear()

            # 3. Log the decision (extract and remove the trace before passing to oracle)
            llm_trace = action.pop("_llm_trace", None)
            planning_trace = action.pop("_planning_trace", None) or {}
            planner_llm = planning_trace.pop("planner_llm", None)
            action_source = "llm" if (llm_trace and llm_trace.get("raw_response")) else "fallback"
            self.event_emitter.emit_agent_decision(
                tick, agent.name, action, parse_ok=(action_source == "llm"),
                llm_trace=llm_trace,
            )
            if "plan_created" in planning_trace:
                self.event_emitter.emit_plan_created(tick, agent.name, planning_trace["plan_created"])
            if "plan_updated" in planning_trace:
                self.event_emitter.emit_plan_updated(tick, agent.name, planning_trace["plan_updated"])
            if "plan_abandoned" in planning_trace:
                self.event_emitter.emit_plan_abandoned(tick, agent.name, planning_trace["plan_abandoned"])
            if "subgoal_completed" in planning_trace:
                self.event_emitter.emit_subgoal_completed(
                    tick,
                    agent.name,
                    planning_trace["subgoal_completed"],
                )
            if "subgoal_failed" in planning_trace:
                self.event_emitter.emit_subgoal_failed(
                    tick,
                    agent.name,
                    planning_trace["subgoal_failed"],
                )
            if planner_llm:
                self.sim_logger.log_agent_plan(
                    tick,
                    agent,
                    system_prompt=planner_llm.get("system_prompt", ""),
                    user_prompt=planner_llm.get("user_prompt", ""),
                    raw_response=planner_llm.get("raw_response", ""),
                    parsed_plan=planner_llm.get("parsed_plan", {}),
                )
            if action_source == "llm":
                self.sim_logger.log_agent_decision(
                    tick, agent,
                    system_prompt=llm_trace.get("system_prompt", ""),
                    user_prompt=llm_trace.get("user_prompt", ""),
                    raw_response=llm_trace.get("raw_response", ""),
                    parsed_action=action,
                )
            else:
                self.sim_logger.log_agent_fallback_decision(tick, agent, action)

            print(f"  🧠 {agent.name} decides: {action_str}" + (f" ({reason})" if reason else ""))

            # Emit innovation attempt before validation
            if action_str == "innovate":
                self.event_emitter.emit_innovation_attempt(tick, agent.name, action)

            # 4. Oracle resolves the action
            result = self.oracle.resolve_action(agent, action, tick)
            self.event_emitter.emit_oracle_resolution(
                tick, agent.name, result,
                llm_trace=self.oracle.last_llm_trace,
                oracle_context=self.oracle.last_llm_context,
                cache_hit=self.oracle.last_cache_hit,
            )
            if action_str == "innovate":
                self.event_emitter.emit_innovation_validated(
                    tick, agent.name, result,
                    requires=action.get("requires"), produces=action.get("produces"),
                )
            elif action_str not in _BASE_ACTIONS:
                self.event_emitter.emit_custom_action_executed(tick, agent.name, action, result)

            # Emit innovation events for item-derived (auto-discovered) innovations
            for derived in result.get("derived_innovations", []):
                attempt = derived.get("attempt", {})
                validation = derived.get("result", {})
                self.event_emitter.emit_innovation_attempt(tick, agent.name, attempt)
                self.event_emitter.emit_innovation_validated(
                    tick, agent.name, validation,
                    requires=attempt.get("requires"),
                    produces=attempt.get("produces"),
                    description=attempt.get("description"),
                    origin_item=derived.get("origin_item"),
                    discovery_mode=derived.get("discovery_mode"),
                    trigger_action=derived.get("trigger_action"),
                )

            # 4c. Evaluate active subgoal progress after oracle resolution
            _subgoal = agent.current_subgoal()
            if _subgoal is not None:
                _consecutive = getattr(agent.planning_state, "_subgoal_fail_streak", 0)
                if check_completion(_subgoal, agent, result, action_str):
                    agent.planning_state.active_subgoal_index += 1
                    agent.planning_state._subgoal_fail_streak = 0  # type: ignore[attr-defined]
                    self.event_emitter.emit_subgoal_completed(tick, agent.name, {
                        "subgoal": _subgoal.description,
                        "kind": _subgoal.kind,
                    })
                elif check_failure(_subgoal, agent, result, action_str, _consecutive):
                    agent.planning_state.status = "blocked"
                    agent.planning_state._subgoal_fail_streak = 0  # type: ignore[attr-defined]
                    self.event_emitter.emit_subgoal_failed(tick, agent.name, {
                        "subgoal": _subgoal.description,
                        "kind": _subgoal.kind,
                    })
                elif not result.get("success"):
                    agent.planning_state._subgoal_fail_streak = _consecutive + 1  # type: ignore[attr-defined]

            crafting_event = result.get("crafting_event")
            status = "✅" if result["success"] else "❌"

            # Append crafting summary to console output when crafting occurred
            crafting_suffix = ""
            if crafting_event and (crafting_event.get("consumed") or crafting_event.get("produced")):
                c_str = ", ".join(f"-{q}x{i}" for i, q in crafting_event["consumed"].items())
                p_str = ", ".join(f"+{q}x{i}" for i, q in crafting_event["produced"].items())
                parts = [s for s in [c_str, p_str] if s]
                crafting_suffix = f"  [CRAFTED: {' '.join(parts)}]"
            print(f"     {status} {result['message']}{crafting_suffix}")

            # Collect event for web broadcast
            self._tick_events.append({
                "agent": agent.name,
                "action": action_str,
                "success": result["success"],
                "message": result["message"],
            })

            # Accumulate for W&B
            if self.wandb_logger:
                tick_data["actions"].append(action_str)
                tick_data["oracle_results"].append(result["success"])

            # 4b. Handle child spawning from reproduce action
            child_spawn = result.get("child_spawn")
            if child_spawn and result["success"]:
                child = self._spawn_child(
                    parent_a_name=child_spawn["parent_a"],
                    parent_b_name=child_spawn["parent_b"],
                    pos=child_spawn["pos"],
                    tick=tick,
                )
                self.event_emitter.emit_agent_birth(tick, child)
                self.agents.append(child)
                alive_agents.append(child)
                if self.wandb_logger:
                    tick_data["births"] += 1
                self.oracle.current_tick_agents = alive_agents
                print(f"     👶 {child.name} was born at {child_spawn['pos']}! "
                      f"(Gen {child.generation}, parents: {child_spawn['parent_a']} & {child_spawn['parent_b']})")

            # 5. Log oracle resolution (with inventory diff and crafting event)
            self.sim_logger.log_oracle_resolution(
                tick, agent, action, result,
                inventory_before=inventory_before,
                crafting_event=crafting_event,
            )

            # 6. Apply passive tick effects (hunger, etc.)
            prev_life = agent.life
            prev_hunger = agent.hunger
            agent.apply_tick_effects()
            effects_parts = []
            if agent.hunger != prev_hunger:
                effects_parts.append(f"Hunger {prev_hunger} -> {agent.hunger}")
            if agent.life != prev_life:
                effects_parts.append(f"Life {prev_life} -> {agent.life}")
            if not agent.alive:
                effects_parts.append("DIED")
                self.lineage.record_death(agent.name, tick)
                if self.wandb_logger:
                    tick_data["deaths"] += 1
            if effects_parts:
                self.sim_logger.log_tick_effects(tick, agent, "; ".join(effects_parts))

            # Track innovations in lineage
            if result.get("success") and result.get("effects", {}).get("new_action"):
                self.lineage.record_innovation(agent.name, result["effects"]["new_action"])
                if self.wandb_logger:
                    tick_data["innovations"] += 1

            self.event_emitter.emit_agent_state(tick, agent)

        # World update: resource regeneration at dawn
        regenerated = self.world.update_resources(tick)
        if regenerated:
            logger.info("[tick %d] %d tree(s) regenerated fruit at dawn", tick, len(regenerated))

        # Log world state (resource changes + day/night period) for this tick
        resources_after = {pos: dict(res) for pos, res in self.world.resources.items()}
        self.sim_logger.log_tick_world_state(
            tick=tick,
            period=self.day_cycle.get_period(tick),
            hour=self.day_cycle.get_hour(tick),
            day=self.day_cycle.get_day(tick),
            resources_before=resources_before,
            resources_after=resources_after,
            regenerated=regenerated,
        )

        # Memory compression
        for agent in alive_agents:
            if agent.alive and agent.memory_system.should_compress(tick):
                episode_count = len(agent.memory_system.episodic)
                learnings = agent.memory_system.compress(llm=self.llm, tick=tick, agent_name=agent.name)
                self.event_emitter.emit_memory_compression_result(
                    tick, agent.name, episode_count=episode_count, learnings=learnings
                )

        # Log tick to W&B
        if self.wandb_logger:
            self.wandb_logger.log_tick(
                tick, alive_agents, self.world, self.oracle, tick_data
            )

        # Show agent states
        self._print_agent_states()

    def _pick_child_name(self, parent_a_name: str, parent_b_name: str) -> str:
        """Pick an unused name from the pool; fall back to generation suffixes."""
        for name in AGENT_NAME_POOL:
            if name not in self._used_names:
                self._used_names.add(name)
                return name
        # Pool exhausted: derive from parent names with generation suffix
        base = parent_a_name[:3] + parent_b_name[:3]
        suffix = 2
        while True:
            candidate = f"{base}-G{suffix}"
            if candidate not in self._used_names:
                self._used_names.add(candidate)
                return candidate
            suffix += 1

    def _spawn_child(
        self,
        parent_a_name: str,
        parent_b_name: str,
        pos: tuple[int, int],
        tick: int,
    ) -> Agent:
        """Create a child agent, apply inheritance, and record in lineage."""
        parent_a = next(a for a in self.agents if a.name == parent_a_name)
        parent_b = next(a for a in self.agents if a.name == parent_b_name)

        name = self._pick_child_name(parent_a_name, parent_b_name)
        child = Agent(name=name, x=pos[0], y=pos[1], llm=self.llm)

        # Override default stats with child (infant) values
        child.life = CHILD_START_LIFE
        child.hunger = CHILD_START_HUNGER
        child.energy = CHILD_START_ENERGY

        # Generational tracking
        child.generation = max(parent_a.generation, parent_b.generation) + 1
        child.parent_ids = [parent_a_name, parent_b_name]
        child.born_tick = tick

        # Personality inheritance via blending
        child.personality = Personality.blend(parent_a.personality, parent_b.personality)

        # Knowledge inheritance: semantic memories from both parents
        child.memory_system.inherit_from(parent_a.memory_system, parent_b.memory_system)

        # Innovation inheritance: only shared innovations (known by both)
        shared_innovations = [
            action for action in parent_a.actions
            if action not in child.actions and action in parent_b.actions
        ]
        child.actions.extend(shared_innovations)
        for act in shared_innovations:
            for parent in (parent_a, parent_b):
                if act in parent.action_descriptions:
                    child.action_descriptions[act] = parent.action_descriptions[act]
                    break

        # Bootstrap relationships: both parents bond with child and vice versa
        child.update_relationship(parent_a_name, delta=BONDING_TRUST_THRESHOLD, tick=tick)
        child.update_relationship(parent_b_name, delta=BONDING_TRUST_THRESHOLD, tick=tick)
        parent_a.update_relationship(name, delta=BONDING_TRUST_THRESHOLD, tick=tick)
        parent_b.update_relationship(name, delta=BONDING_TRUST_THRESHOLD, tick=tick)
        parent_a.children_names.append(name)
        parent_b.children_names.append(name)

        # Lineage recording
        self.lineage.record_birth(name, [parent_a_name, parent_b_name], child.generation, tick)
        self.lineage.record_child(parent_a_name, name)
        self.lineage.record_child(parent_b_name, name)

        logger.info(
            "👶 %s born (gen %d) at %s, parents: %s & %s",
            name, child.generation, pos, parent_a_name, parent_b_name,
        )
        return child

    def _log_overview_start(self):
        """Write initial overview to sim logger."""
        config_summary = {
            "max_ticks": format_tick_limit(self.max_ticks),
            "num_agents": len(self.agents),
            "use_llm": self.use_llm,
            "llm_model": self.llm.model if self.llm else "none",
            "world_size": f"{self.world.width}x{self.world.height}",
        }
        world_summary = self.world.get_summary()
        self.sim_logger.log_overview_start(config_summary, world_summary, self.agents)

    def _print_header(self):
        print("\n" + "=" * 70)
        print("🌍  LIFE SIMULATION - AUTONOMOUS AGENTS")
        print("=" * 70)

        summary = self.world.get_summary()
        print(f"  World: {summary['dimensions']}")
        print(f"  Tiles: 🌊 Water={summary['tile_counts'].get('water', 0)} | "
              f"🟫 Land={summary['tile_counts'].get('land', 0)} | "
              f"🌳 Trees={summary['tile_counts'].get('tree', 0)}")
        fruit_qty = summary["resources_by_type"].get("fruit", 0)
        fruit_locs = sum(1 for r in self.world.resources.values() if r["type"] == "fruit")
        print(f"  Available fruit: {fruit_qty} in {fruit_locs} trees")
        print(f"  Agents: {len(self.agents)}")
        print(f"  LLM: {'✅ ' + self.llm.model if self.llm else '❌ Fallback mode (no LLM)'}")
        print(f"  Max ticks: {format_tick_limit(self.max_ticks)}")

        print("\n  Initial agents:")
        for agent in self.agents:
            print(f"    • {agent.name} at ({agent.x}, {agent.y})")

        print("=" * 70)

    def _print_tick_header(self, tick: int, alive_agents: list[Agent], time_description: str = ""):
        self._print_separator()
        alive_count = len(alive_agents)
        dead_count = len(self.agents) - alive_count
        hour = self.day_cycle.get_hour(tick)
        day = self.day_cycle.get_day(tick)
        period = self.day_cycle.get_period(tick)
        period_icons = {"day": "☀️ ", "sunset": "🌅", "night": "🌙"}
        period_icon = period_icons.get(period, "")
        print(f"\n⏱️  TICK {tick:04d}  |  {period_icon} Day {day}, {hour:02d}:00  |  "
              f"Alive: {alive_count}  |  Dead: {dead_count}")
        print("-" * 50)

    def _print_agent_states(self):
        print()
        for agent in self.agents:
            if agent.alive:
                bar_life = self._bar(agent.life, 100)
                bar_hunger = self._bar(agent.hunger, 100)
                bar_energy = self._bar(agent.energy, 100)
                print(f"  {agent.name:8s} | ❤️ {bar_life} {agent.life:3d} | "
                      f"🍖 {bar_hunger} {agent.hunger:3d} | "
                      f"⚡ {bar_energy} {agent.energy:3d} | "
                      f"📍({agent.x},{agent.y})")
            else:
                print(f"  {agent.name:8s} | 💀 DEAD")

    @staticmethod
    def _bar(value: int, max_val: int, width: int = 10) -> str:
        filled = int(value / max_val * width)
        return "█" * filled + "░" * (width - filled)

    def _print_separator(self):
        pass  # Keeps output clean

    def _log_overview_end(self):
        """Write final summary to sim logger."""
        lines = []
        lines.append(f"**Ticks completed:** {self.current_tick}\n\n")

        alive = [a for a in self.agents if a.alive]
        lines.append(f"**Survivors:** {len(alive)}/{len(self.agents)}\n\n")

        for agent in self.agents:
            status = "ALIVE" if agent.alive else "DEAD"
            lines.append(f"### {agent.name} ({status})\n\n")
            lines.append(f"- Life={agent.life}, Hunger={agent.hunger}, Energy={agent.energy}\n")
            lines.append(f"- Known actions: {', '.join(agent.actions)}\n")
            lines.append(f"- Memory entries: {len(agent.memory)}\n")
            innovated = [a for a in agent.actions if a not in _BASE_ACTIONS]
            if innovated:
                lines.append(f"- Innovations: {', '.join(innovated)}\n")
            lines.append("\n")

        if self.oracle.precedents:
            lines.append(f"### Oracle Precedents ({len(self.oracle.precedents)})\n\n")
            for key, value in list(self.oracle.precedents.items())[:10]:
                lines.append(f"- `{key}`: {value}\n")
            lines.append("\n")

        self.sim_logger.log_overview_end("".join(lines))

    def _print_summary(self):
        print("\n" + "=" * 70)
        print("📊  FINAL SUMMARY")
        print("=" * 70)
        print(f"  Ticks completed: {self.current_tick}")

        alive = [a for a in self.agents if a.alive]
        dead = [a for a in self.agents if not a.alive]

        print(f"  Survivors: {len(alive)}/{len(self.agents)}")

        for agent in self.agents:
            status = "🟢 ALIVE" if agent.alive else "🔴 DEAD"
            print(f"\n  {agent.name} ({status})")
            print(f"    Final stats: Life={agent.life}, Hunger={agent.hunger}, Energy={agent.energy}")
            print(f"    Known actions: {', '.join(agent.actions)}")
            print(f"    Memory entries: {len(agent.memory)}")

            # Show innovated actions
            innovated = [a for a in agent.actions if a not in _BASE_ACTIONS]
            if innovated:
                print(f"    🆕 Innovations: {', '.join(innovated)}")

        # Show oracle precedents
        if self.oracle.precedents:
            print(f"\n  📖 Oracle Precedents: {len(self.oracle.precedents)}")
            for key, value in list(self.oracle.precedents.items())[:10]:
                print(f"    • {key}: {value}")

        # World summary
        summary = self.world.get_summary()
        print(f"\n  🌍 Final world state:")
        remaining_fruit_qty = summary["resources_by_type"].get("fruit", 0)
        remaining_fruit_locs = sum(1 for r in self.world.resources.values() if r["type"] == "fruit")
        print(f"    Remaining fruit: {remaining_fruit_qty} in {remaining_fruit_locs} trees")

        print("\n" + "=" * 70)

        # Write final overview to log folder
        self._log_overview_end()

        print(f"  📂 Detailed logs: {self.sim_logger.run_dir}/")

    # ------------------------------------------------------------------
    # Web server integration
    # ------------------------------------------------------------------

    def run_with_callback(
        self,
        on_tick: Callable[[dict], None],
        pause_flag: Optional[threading.Event] = None,
    ) -> None:
        """
        Run the simulation, calling on_tick(msg) after every tick.
        Designed to be called from a background thread by the web server.
        The sync run() method is unaffected.

        pause_flag: a threading.Event that, when set, pauses the tick loop.
        """
        # Skip emoji console decorations (breaks on Windows cp1252 terminals).
        # The web server uses structured logging instead.
        self._log_overview_start()
        self.event_emitter.emit_run_start(
            agent_names=[a.name for a in self.agents],
            model_id=self.llm.model if self.llm else "none",
            world_seed=self._world_seed,
            width=self.world.width,
            height=self.world.height,
            max_ticks=self.max_ticks,
            agent_profiles=[self._agent_profile(a) for a in self.agents],
        )

        try:
            for tick in iter_tick_numbers(self.max_ticks):
                # Honour pause requests
                if pause_flag is not None:
                    while pause_flag.is_set():
                        time.sleep(0.05)

                alive_agents = [a for a in self.agents if a.alive]

                if not alive_agents:
                    logger.info("All agents have died — simulation complete")
                    break

                self.current_tick = tick
                self._tick_events = []
                self._run_tick(tick, alive_agents)

                on_tick({
                    "type": "tick",
                    "tick": tick,
                    "agents": [self._serialize_agent(a) for a in self.agents],
                    "events": list(self._tick_events),
                    "world_resources": {
                        f"{x},{y}": res
                        for (x, y), res in self.world.resources.items()
                    },
                })

                if TICK_DELAY_SECONDS > 0:
                    time.sleep(TICK_DELAY_SECONDS)
        finally:
            self.oracle.save_precedents(
                self._precedents_path, self.current_tick, self._world_seed
            )
            self.lineage.save(self._lineage_path)
            survivors = [a.name for a in self.agents if a.alive]
            self.event_emitter.emit_run_end(self.current_tick, survivors, self.current_tick)
            self.event_emitter.close()
            try:
                MetricsBuilder(self.event_emitter.run_dir).build()
                EBSBuilder(self.event_emitter.run_dir).build()
            except Exception as exc:
                logger.warning("MetricsBuilder/EBSBuilder failed: %s", exc)
            if self.run_digest:
                try:
                    from simulation.digest.digest_builder import DigestBuilder
                    DigestBuilder(self.event_emitter.run_dir).build()
                except Exception as exc:
                    logger.warning("DigestBuilder failed: %s", exc)
            if self.wandb_logger:
                try:
                    self.wandb_logger.log_post_run(
                        self.event_emitter.run_dir,
                        include_digest=self.run_digest,
                    )
                except Exception as exc:
                    logger.warning("W&B post-run log failed: %s", exc)
                self.wandb_logger.finish()

        self._log_overview_end()

    def get_init_message(self) -> dict:
        """Build the initial state message for a new WebSocket connection."""
        return {
            "type": "init",
            "tick": self.current_tick,
            "world": {
                "width": self.world.width,
                "height": self.world.height,
                "tiles": [
                    [self.world.grid[y][x] for x in range(self.world.width)]
                    for y in range(self.world.height)
                ],
                "resources": {
                    f"{x},{y}": res
                    for (x, y), res in self.world.resources.items()
                },
            },
            "agents": [self._serialize_agent(a) for a in self.agents],
        }

    @staticmethod
    def _serialize_agent(agent) -> dict:
        return {
            "id": agent.id,
            "name": agent.name,
            "x": agent.x,
            "y": agent.y,
            "life": agent.life,
            "hunger": agent.hunger,
            "energy": agent.energy,
            "alive": agent.alive,
            "actions": list(agent.actions),
            "memory": list(agent.memory[-10:]),
        }

    def save_world_log(self, filepath: str = "simulation_log.txt"):
        """Save the complete world log to a file."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("SIMULATION LOG\n")
            f.write("=" * 50 + "\n\n")
            for entry in self.oracle.world_log:
                f.write(entry + "\n")

            f.write("\n\nAGENT MEMORIES\n")
            f.write("=" * 50 + "\n")
            for agent in self.agents:
                f.write(f"\n--- {agent.name} ---\n")
                for mem in agent.memory:
                    f.write(f"  {mem}\n")
        logger.info(f"Log saved to {filepath}")

    def save_world_state(self, filepath: str = "world_state.json"):
        """Save the world state as JSON."""
        state = {
            "tick": self.current_tick,
            "world_summary": self.world.get_summary(),
            "agents": [a.get_status() for a in self.agents],
            "oracle_precedents": {k: str(v) for k, v in self.oracle.precedents.items()},
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logger.info(f"World state saved to {filepath}")
