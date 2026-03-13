"""
Per-simulation structured logger.

Creates a folder per run with human-readable markdown files:
  logs/sim_<timestamp>/
    overview.md        — config, world summary, agent roster, final results
    tick_NNNN.md       — all agent decisions + oracle resolutions for that tick
    agents/<Name>.md   — per-agent history across all ticks
    oracle.md          — all oracle LLM calls
"""

import json
import os
from datetime import datetime

from simulation.config import LOG_DIR


class SimLogger:
    """Writes structured markdown logs for a single simulation run."""

    def __init__(self):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.run_dir = os.path.join(LOG_DIR, f"sim_{timestamp}")
        self.agents_dir = os.path.join(self.run_dir, "agents")
        os.makedirs(self.agents_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _append(self, filename: str, text: str):
        path = os.path.join(self.run_dir, filename)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)

    def _agent_file(self, agent_name: str) -> str:
        return os.path.join("agents", f"{agent_name}.md")

    @staticmethod
    def _stats_line(agent) -> str:
        return (
            f"Life={agent.life} | Hunger={agent.hunger} | "
            f"Energy={agent.energy} | Pos=({agent.x},{agent.y})"
        )

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------

    def log_overview_start(self, config_summary: dict, world_summary: dict, agents):
        """Write the initial overview file with config, world, and agent info."""
        lines = [
            "# Simulation Overview\n\n",
            f"**Started:** {datetime.now().isoformat()}\n\n",
            "## Configuration\n\n",
        ]
        for k, v in config_summary.items():
            lines.append(f"- **{k}:** {v}\n")

        lines.append("\n## World\n\n")
        for k, v in world_summary.items():
            lines.append(f"- **{k}:** {v}\n")

        lines.append("\n## Agents\n\n")
        for agent in agents:
            lines.append(f"- **{agent.name}** at ({agent.x},{agent.y})\n")

        lines.append("\n---\n\n")
        self._append("overview.md", "".join(lines))

    def log_overview_end(self, summary_text: str):
        """Append final summary to overview."""
        lines = [
            "## Final Summary\n\n",
            f"**Ended:** {datetime.now().isoformat()}\n\n",
            summary_text,
            "\n",
        ]
        self._append("overview.md", "".join(lines))

    # ------------------------------------------------------------------
    # Tick files
    # ------------------------------------------------------------------

    def log_tick_start(self, tick: int, alive_agents):
        """Create / start the tick file header."""
        lines = [
            f"# Tick {tick:04d}\n\n",
            f"**Alive agents:** {', '.join(a.name for a in alive_agents)}\n\n",
        ]
        self._append(f"tick_{tick:04d}.md", "".join(lines))

    def log_agent_decision(self, tick: int, agent, system_prompt: str,
                           user_prompt: str, raw_response: str, parsed_action: dict):
        """Log an agent's LLM decision to the tick file and the agent file."""
        block = self._format_decision_block(
            agent, system_prompt, user_prompt, raw_response, parsed_action
        )

        # Tick file
        self._append(f"tick_{tick:04d}.md", block)

        # Agent file
        agent_block = f"## Tick {tick:04d}\n\n{block}"
        self._append(self._agent_file(agent.name), agent_block)

    def log_agent_fallback_decision(self, tick: int, agent, parsed_action: dict):
        """Log a fallback (no-LLM) decision."""
        action_str = parsed_action.get("action", "none")
        reason = parsed_action.get("reason", "")
        block = (
            f"### {agent.name}\n\n"
            f"**Stats before:** {self._stats_line(agent)}\n\n"
            f"**Decision (fallback):** `{action_str}`\n"
            f"**Reason:** {reason}\n\n"
        )
        self._append(f"tick_{tick:04d}.md", block)
        self._append(self._agent_file(agent.name), f"## Tick {tick:04d}\n\n{block}")

    def log_agent_plan(
        self,
        tick: int,
        agent,
        system_prompt: str,
        user_prompt: str,
        raw_response: str,
        parsed_plan: dict,
    ):
        """Log planner LLM details to the per-agent file only."""
        block = self._format_planner_block(
            system_prompt,
            user_prompt,
            raw_response,
            parsed_plan,
        )
        self._append(self._agent_file(agent.name), f"## Tick {tick:04d}\n\n{block}")

    def log_oracle_resolution(
        self,
        tick: int,
        agent,
        action: dict,
        result: dict,
        inventory_before: dict | None = None,
        crafting_event: dict | None = None,
    ):
        """Log the oracle resolution to tick + agent files."""
        status = "SUCCESS" if result["success"] else "FAILED"
        block = (
            f"**Oracle resolution:** {status}\n"
            f"**Message:** {result['message']}\n"
            f"**Effects:** {result.get('effects', {})}\n\n"
            f"**Stats after:** {self._stats_line(agent)}\n\n"
            "---\n\n"
        )

        if inventory_before is not None:
            inv_after = dict(agent.inventory.items)
            all_keys = set(inventory_before) | set(inv_after)
            changes = []
            for k in sorted(all_keys):
                b = inventory_before.get(k, 0)
                a = inv_after.get(k, 0)
                if a > b:
                    changes.append(f"+{a - b} {k}")
                elif a < b:
                    changes.append(f"-{b - a} {k}")
            inv_before_str = (
                ", ".join(f"{k}={v}" for k, v in sorted(inventory_before.items()))
                or "empty"
            )
            inv_after_str = (
                ", ".join(f"{k}={v}" for k, v in sorted(inv_after.items())) or "empty"
            )
            changes_str = ", ".join(changes) or "no change"
            inv_block = (
                f"**Inventory before:** {inv_before_str}\n"
                f"**Inventory after:** {inv_after_str} ({changes_str})\n\n"
            )
            block = block.replace("---\n\n", inv_block + "---\n\n", 1)

        if crafting_event and (crafting_event.get("consumed") or crafting_event.get("produced")):
            consumed_str = (
                ", ".join(f"{q}x {i}" for i, q in crafting_event["consumed"].items())
                or "nothing"
            )
            produced_str = (
                ", ".join(f"{q}x {i}" for i, q in crafting_event["produced"].items())
                or "nothing"
            )
            craft_block = f"**Crafting:** consumed [{consumed_str}] -> produced [{produced_str}]\n\n"
            block = block.replace("---\n\n", craft_block + "---\n\n", 1)

        self._append(f"tick_{tick:04d}.md", block)
        self._append(self._agent_file(agent.name), block)

    # ------------------------------------------------------------------
    # Oracle LLM calls
    # ------------------------------------------------------------------

    def log_oracle_llm_call(self, tick: int, context: str,
                            system_prompt: str, user_prompt: str,
                            raw_response: str, parsed_result):
        """Log an oracle LLM call to oracle.md."""
        block = (
            f"## Tick {tick:04d} — {context}\n\n"
            f"### System prompt\n\n```\n{system_prompt}\n```\n\n"
            f"### User prompt\n\n```\n{user_prompt}\n```\n\n"
            f"### Raw response\n\n```\n{raw_response}\n```\n\n"
            f"### Parsed result\n\n```json\n{parsed_result}\n```\n\n"
            "---\n\n"
        )
        self._append("oracle.md", block)

    # ------------------------------------------------------------------
    # Tick effects
    # ------------------------------------------------------------------

    def log_tick_effects(self, tick: int, agent, effects_description: str):
        """Log passive tick effects (hunger increase, damage, death)."""
        block = f"**Tick effects for {agent.name}:** {effects_description}\n\n"
        self._append(f"tick_{tick:04d}.md", block)
        self._append(self._agent_file(agent.name), block)

    def log_tick_world_state(
        self,
        tick: int,
        period: str,
        hour: int,
        day: int,
        resources_before: dict,
        resources_after: dict,
        regenerated: list,
    ) -> None:
        """Append world-state summary (resources consumed, regenerated) to the tick file."""
        period_icons = {"day": "☀️", "sunset": "🌅", "night": "🌙"}
        icon = period_icons.get(period, "")

        harvested = []
        all_positions = set(resources_before) | set(resources_after)
        for pos in sorted(all_positions):
            before = resources_before.get(pos)
            after = resources_after.get(pos)
            if before and (not after or after["quantity"] < before["quantity"]):
                delta = before["quantity"] - (after["quantity"] if after else 0)
                harvested.append(f"({pos[0]},{pos[1]}) {before['type']} -{delta}")

        lines = [f"## World State — {icon} {period.capitalize()} (Day {day}, {hour:02d}:00)\n\n"]
        lines.append(
            "**Resources consumed this tick:** "
            + (", ".join(harvested) if harvested else "none")
            + "\n\n"
        )
        if regenerated:
            regen_str = ", ".join(f"({x},{y})" for x, y in regenerated)
            lines.append(f"**Regenerated at dawn:** {regen_str}\n\n")
        lines.append("---\n\n")

        self._append(f"tick_{tick:04d}.md", "".join(lines))

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_decision_block(agent, system_prompt, user_prompt,
                                raw_response, parsed_action) -> str:
        action_str = parsed_action.get("action", "none")
        reason = parsed_action.get("reason", "")
        return (
            f"### {agent.name}\n\n"
            f"**Stats before:** Life={agent.life} | Hunger={agent.hunger} | "
            f"Energy={agent.energy} | Pos=({agent.x},{agent.y})\n\n"
            f"**Parsed action:** `{action_str}`\n"
            f"**Reason:** {reason}\n\n"
            f"<details>\n<summary>System prompt</summary>\n\n"
            f"```\n{system_prompt}\n```\n\n</details>\n\n"
            f"<details>\n<summary>User prompt</summary>\n\n"
            f"```\n{user_prompt}\n```\n\n</details>\n\n"
            f"<details>\n<summary>Raw LLM response</summary>\n\n"
            f"```\n{raw_response}\n```\n\n</details>\n\n"
        )

    @staticmethod
    def _format_planner_block(system_prompt, user_prompt, raw_response, parsed_plan) -> str:
        parsed_json = json.dumps(parsed_plan, indent=2, sort_keys=True)
        return (
            "### Planner\n\n"
            "<details>\n<summary>System prompt</summary>\n\n"
            f"```\n{system_prompt}\n```\n\n</details>\n\n"
            "<details>\n<summary>Planner prompt</summary>\n\n"
            f"```\n{user_prompt}\n```\n\n</details>\n\n"
            "<details>\n<summary>Raw LLM response</summary>\n\n"
            f"```\n{raw_response}\n```\n\n</details>\n\n"
            f"### Parsed plan\n\n```json\n{parsed_json}\n```\n\n"
        )
