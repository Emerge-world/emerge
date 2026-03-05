"""
Simulation engine: orchestrates the main tick loop.
"""

import time
import json
import logging
import threading
from typing import Optional, Callable

from simulation.config import (
    MAX_AGENTS, MAX_TICKS, TICK_DELAY_SECONDS,
    AGENT_VISION_RADIUS, WORLD_WIDTH, WORLD_HEIGHT, WORLD_START_HOUR,
)
from simulation.world import World
from simulation.agent import Agent
from simulation.oracle import Oracle
from simulation.llm_client import LLMClient
from simulation.sim_logger import SimLogger
from simulation.audit_recorder import AuditRecorder
from simulation.day_cycle import DayCycle

logger = logging.getLogger(__name__)


class SimulationEngine:
    """Main simulation engine."""

    def __init__(
        self,
        num_agents: int = 3,
        world_seed: Optional[int] = None,
        use_llm: bool = True,
        max_ticks: int = MAX_TICKS,
        audit: bool = False,
        start_hour: int = WORLD_START_HOUR,
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
            self.llm = LLMClient()
            if not self.llm.is_available():
                logger.warning("⚠️  Ollama is not available. Running in fallback mode (no LLM).")
                self.llm = None
                self.use_llm = False

        # Day/night cycle
        self.day_cycle = DayCycle(start_hour=start_hour)

        # Create world
        self.world = World(seed=world_seed)

        # Create simulation logger
        self.sim_logger = SimLogger()

        # Create oracle
        self.oracle = Oracle(self.world, llm=self.llm, sim_logger=self.sim_logger,
                             day_cycle=self.day_cycle)

        # Auto-load precedents from previous runs
        self.oracle.load_precedents(self._precedents_path)

        # Create agents
        num_agents = min(num_agents, MAX_AGENTS)
        self.agents: list[Agent] = []
        for i in range(num_agents):
            x, y = self.world.find_spawn_point()
            agent = Agent(x=x, y=y, llm=self.llm)
            self.agents.append(agent)

        # Web server: per-tick event collector (populated by run_with_callback)
        self._tick_events: list[dict] = []

        # Audit recorder
        self.recorder: Optional[AuditRecorder] = None
        if audit:
            audit_config = {
                "max_ticks": max_ticks,
                "num_agents": num_agents,
                "use_llm": self.use_llm,
                "world_seed": world_seed,
                "world_size": f"{WORLD_WIDTH}x{WORLD_HEIGHT}",
            }
            self.recorder = AuditRecorder(self.sim_logger.run_dir, audit_config)

        logger.info(f"Simulation initialized: {num_agents} agents, world {WORLD_WIDTH}x{WORLD_HEIGHT}")

    def run(self):
        """Run the complete simulation."""
        self._print_header()
        self._log_overview_start()

        try:
            for tick in range(1, self.max_ticks + 1):
                self.current_tick = tick
                alive_agents = [a for a in self.agents if a.alive]

                if not alive_agents:
                    self._print_separator()
                    print("\n☠️  ALL AGENTS HAVE DIED. End of simulation.")
                    break

                self._run_tick(tick, alive_agents)

                if TICK_DELAY_SECONDS > 0:
                    time.sleep(TICK_DELAY_SECONDS)
        finally:
            self.oracle.save_precedents(
                self._precedents_path, self.current_tick, self._world_seed
            )

        self._print_summary()

    def _run_tick(self, tick: int, alive_agents: list[Agent]):
        """Execute a complete tick."""
        vision_radius = self.day_cycle.get_vision_radius(tick)
        time_description = self.day_cycle.get_prompt_line(tick)

        self._print_tick_header(tick, alive_agents, time_description)
        self.sim_logger.log_tick_start(tick, alive_agents)

        for agent in alive_agents:
            if not agent.alive:
                continue

            # 1. Get environment perception (radius varies by time of day)
            nearby = self.world.get_nearby_tiles(agent.x, agent.y, vision_radius)

            # Audit: snapshot stats before action
            if self.recorder:
                stats_before = {"life": agent.life, "hunger": agent.hunger, "energy": agent.energy}
                position_before = (agent.x, agent.y)

            # 2. Agent decides its action
            action = agent.decide_action(nearby, tick, time_description)
            action_str = action.get("action", "none")
            reason = action.get("reason", "")

            # 3. Log the decision (extract and remove the trace before passing to oracle)
            llm_trace = action.pop("_llm_trace", None)
            action_source = "llm" if (llm_trace and llm_trace.get("raw_response")) else "fallback"
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

            # 4. Oracle resolves the action
            result = self.oracle.resolve_action(agent, action, tick)
            status = "✅" if result["success"] else "❌"
            print(f"     {status} {result['message']}")

            # Collect event for web broadcast
            self._tick_events.append({
                "agent": agent.name,
                "action": action_str,
                "success": result["success"],
                "message": result["message"],
            })

            # 5. Log oracle resolution
            self.sim_logger.log_oracle_resolution(tick, agent, action, result)

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
            if effects_parts:
                self.sim_logger.log_tick_effects(tick, agent, "; ".join(effects_parts))

            # Audit: record event after all effects applied
            if self.recorder:
                stats_after = {"life": agent.life, "hunger": agent.hunger, "energy": agent.energy}
                self.recorder.record_event(
                    tick=tick,
                    agent_name=agent.name,
                    stats_before=stats_before,
                    position_before=position_before,
                    action=action_str,
                    action_source=action_source,
                    oracle_success=result["success"],
                    effects=result.get("effects", {}),
                    stats_after=stats_after,
                    position_after=(agent.x, agent.y),
                    nearby_tiles=nearby,
                )

        # World update: resource regeneration at dawn
        regenerated = self.world.update_resources(tick)
        if regenerated:
            logger.info("[tick %d] %d tree(s) regenerated fruit at dawn", tick, len(regenerated))

        # Memory compression
        for agent in alive_agents:
            if agent.alive and agent.memory_system.should_compress(tick):
                agent.memory_system.compress(llm=self.llm, tick=tick, agent_name=agent.name)

        # Show agent states
        self._print_agent_states()

    def _log_overview_start(self):
        """Write initial overview to sim logger."""
        config_summary = {
            "max_ticks": self.max_ticks,
            "num_agents": len(self.agents),
            "use_llm": self.use_llm,
            "llm_model": self.llm.model if self.llm else "none",
            "world_size": f"{WORLD_WIDTH}x{WORLD_HEIGHT}",
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
        print(f"  Max ticks: {self.max_ticks}")

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
            innovated = [a for a in agent.actions if a not in ["move", "eat", "rest", "innovate"]]
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
            innovated = [a for a in agent.actions if a not in ["move", "eat", "rest", "innovate"]]
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

        # Finalize audit recording
        if self.recorder:
            self.recorder.finalize(self.max_ticks)
            print(f"  📊 Audit data: {self.recorder.audit_dir}/")

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

        try:
            for tick in range(1, self.max_ticks + 1):
                # Honour pause requests
                if pause_flag is not None:
                    while pause_flag.is_set():
                        time.sleep(0.05)

                self.current_tick = tick
                alive_agents = [a for a in self.agents if a.alive]

                if not alive_agents:
                    logger.info("All agents have died — simulation complete")
                    break

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
