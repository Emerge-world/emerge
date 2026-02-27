"""
Per-simulation structured logger.

Creates a folder per run with human-readable markdown files:
  logs/sim_<timestamp>/
    overview.md        — config, world summary, agent roster, final results
    tick_NNNN.md       — all agent decisions + oracle resolutions for that tick
    agents/<Name>.md   — per-agent history across all ticks
    oracle.md          — all oracle LLM calls
"""

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

    def log_oracle_resolution(self, tick: int, agent, action: dict, result: dict):
        """Log the oracle resolution to tick + agent files."""
        status = "SUCCESS" if result["success"] else "FAILED"
        block = (
            f"**Oracle resolution:** {status}\n"
            f"**Message:** {result['message']}\n"
            f"**Effects:** {result.get('effects', {})}\n\n"
            f"**Stats after:** {self._stats_line(agent)}\n\n"
            "---\n\n"
        )
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
