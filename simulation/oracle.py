"""
Oracle: validates and resolves agent actions.
Maintains a decision memory for determinism (consistency).
"""

import logging
from typing import Optional

from simulation.config import (
    ENERGY_COST_MOVE, ENERGY_COST_EAT, ENERGY_COST_INNOVATE,
    ENERGY_RECOVERY_REST,
)
from simulation.llm_client import LLMClient
from simulation.world import World
from simulation.agent import Agent

logger = logging.getLogger(__name__)


class Oracle:
    """
    The oracle is the world's arbiter.
    Validates actions, determines outcomes, and maintains consistency.
    """

    def __init__(self, world: World, llm: Optional[LLMClient] = None, sim_logger=None):
        self.world = world
        self.llm = llm
        self.sim_logger = sim_logger

        # Oracle memory: stores precedents for determinism
        # Key: descriptive string of the situation -> result
        self.precedents: dict[str, dict] = {}

        # Log of everything that has happened in the world
        self.world_log: list[str] = []

    def resolve_action(self, agent: Agent, action: dict, tick: int) -> dict:
        """
        Resolve an agent's action. Returns the result.

        Returns:
            dict with: {"success": bool, "message": str, "effects": dict}
        """
        action_type = action.get("action", "none")

        if action_type == "move":
            return self._resolve_move(agent, action, tick)
        elif action_type == "eat":
            return self._resolve_eat(agent, action, tick)
        elif action_type == "rest":
            return self._resolve_rest(agent, action, tick)
        elif action_type == "innovate":
            return self._resolve_innovate(agent, action, tick)
        elif action_type in agent.actions:
            # Previously innovated action
            return self._resolve_custom_action(agent, action, tick)
        else:
            return {
                "success": False,
                "message": f"Unknown action: {action_type}",
                "effects": {},
            }

    # --- Base actions ---

    def _resolve_move(self, agent: Agent, action: dict, tick: int) -> dict:
        direction = action.get("direction", "north")
        dx, dy = 0, 0
        if direction == "north":
            dy = -1
        elif direction == "south":
            dy = 1
        elif direction == "east":
            dx = 1
        elif direction == "west":
            dx = -1
        else:
            return {"success": False, "message": f"Invalid direction: {direction}", "effects": {}}

        new_x = agent.x + dx
        new_y = agent.y + dy

        if not self.world.is_walkable(new_x, new_y):
            tile = self.world.get_tile(new_x, new_y)
            reason = "out of bounds" if tile is None else f"there is {tile}"
            msg = f"{agent.name} cannot move {direction}: {reason}."
            self._log(tick, msg)
            agent.add_memory(f"I tried to move {direction} but couldn't: {reason}.")
            return {"success": False, "message": msg, "effects": {}}

        # Success
        agent.x = new_x
        agent.y = new_y
        agent.modify_energy(-ENERGY_COST_MOVE)

        tile_type = self.world.get_tile(new_x, new_y)
        msg = f"{agent.name} moved {direction} → ({new_x},{new_y}) [tile: {tile_type}]."
        self._log(tick, msg)
        agent.add_memory(f"I moved {direction} to ({new_x},{new_y}). There is {tile_type}. Energy: {agent.energy}.")

        return {"success": True, "message": msg, "effects": {"energy": -ENERGY_COST_MOVE}}

    def _resolve_eat(self, agent: Agent, action: dict, tick: int) -> dict:
        # Look for food at current or adjacent tiles
        positions_to_check = [
            (agent.x, agent.y),
            (agent.x + 1, agent.y), (agent.x - 1, agent.y),
            (agent.x, agent.y + 1), (agent.x, agent.y - 1),
        ]

        for (x, y) in positions_to_check:
            resource = self.world.get_resource(x, y)
            if resource and resource["type"] == "fruit":
                consumed = self.world.consume_resource(x, y, 1)
                if consumed > 0:
                    # Look up precedent for how much a fruit reduces hunger
                    hunger_reduction = self._get_fruit_effect(tick)
                    agent.modify_hunger(-hunger_reduction)
                    agent.modify_energy(-ENERGY_COST_EAT)

                    msg = f"{agent.name} ate fruit at ({x},{y}). Hunger -{hunger_reduction} → {agent.hunger}."
                    self._log(tick, msg)
                    agent.add_memory(
                        f"I ate a fruit. My hunger decreased by {hunger_reduction} to {agent.hunger}. Energy: {agent.energy}."
                    )
                    return {
                        "success": True,
                        "message": msg,
                        "effects": {"hunger": -hunger_reduction, "energy": -ENERGY_COST_EAT},
                    }

        msg = f"{agent.name} tried to eat but there's no food nearby."
        self._log(tick, msg)
        agent.add_memory("I tried to eat but couldn't find food within reach.")
        return {"success": False, "message": msg, "effects": {}}

    def _resolve_rest(self, agent: Agent, action: dict, tick: int) -> dict:
        agent.modify_energy(ENERGY_RECOVERY_REST)
        msg = f"{agent.name} rested. Energy +{ENERGY_RECOVERY_REST} → {agent.energy}."
        self._log(tick, msg)
        agent.add_memory(f"I rested and recovered energy. Energy: {agent.energy}.")
        return {
            "success": True,
            "message": msg,
            "effects": {"energy": ENERGY_RECOVERY_REST},
        }

    def _resolve_innovate(self, agent: Agent, action: dict, tick: int) -> dict:
        new_action_name = action.get("new_action_name", "").strip().lower()
        description = action.get("description", "")

        if not new_action_name:
            msg = f"{agent.name} tried to innovate but didn't propose any action."
            self._log(tick, msg)
            return {"success": False, "message": msg, "effects": {}}

        if new_action_name in agent.actions:
            msg = f"{agent.name} tried to innovate '{new_action_name}' but already knows it."
            self._log(tick, msg)
            return {"success": False, "message": msg, "effects": {}}

        # Ask the oracle LLM to validate if the innovation makes sense
        if self.llm:
            validation = self._validate_innovation(agent, new_action_name, description, tick)
            if not validation["approved"]:
                msg = f"{agent.name} tried to innovate '{new_action_name}' but the world doesn't allow it: {validation['reason']}."
                self._log(tick, msg)
                agent.add_memory(f"I tried to create the action '{new_action_name}' but it didn't work: {validation['reason']}.")
                return {"success": False, "message": msg, "effects": {}}

        # Approve innovation
        agent.actions.append(new_action_name)
        agent.modify_energy(-ENERGY_COST_INNOVATE)

        # Register the new action as a precedent
        self.precedents[f"innovation:{new_action_name}"] = {
            "creator": agent.name,
            "description": description,
            "tick_created": tick,
        }

        msg = f"🆕 {agent.name} innovated a new action: '{new_action_name}' - {description}."
        self._log(tick, msg)
        agent.add_memory(
            f"I invented a new action: '{new_action_name}'! {description}. Energy: {agent.energy}."
        )

        logger.info(msg)
        return {
            "success": True,
            "message": msg,
            "effects": {"energy": -ENERGY_COST_INNOVATE, "new_action": new_action_name},
        }

    # --- Innovated (custom) actions ---

    def _resolve_custom_action(self, agent: Agent, action: dict, tick: int) -> dict:
        action_type = action.get("action")
        precedent_key = f"innovation:{action_type}"

        # Look up information about this action
        precedent = self.precedents.get(precedent_key, {})
        description = precedent.get("description", "unknown action")

        # Check if there's already a precedent result for this specific situation
        situation_key = f"custom_action:{action_type}:tile:{self.world.get_tile(agent.x, agent.y)}"
        existing_result = self.precedents.get(situation_key)

        if existing_result:
            # Use precedent result (determinism)
            return self._apply_custom_result(agent, action_type, existing_result, tick)

        if not self.llm:
            # Without LLM, generic effect
            result = {"success": True, "message": f"{agent.name} performed '{action_type}'.", "effects": {"energy": -5}}
            agent.modify_energy(-5)
            self._log(tick, result["message"])
            return result

        # Ask the oracle to determine the outcome
        oracle_result = self._oracle_judge_custom_action(agent, action, description, tick)

        if oracle_result:
            # Save as precedent for determinism
            self.precedents[situation_key] = oracle_result
            return self._apply_custom_result(agent, action_type, oracle_result, tick)

        # Fallback
        agent.modify_energy(-5)
        msg = f"{agent.name} tried '{action_type}' with uncertain results."
        self._log(tick, msg)
        agent.add_memory(f"I performed '{action_type}' but I'm not sure of the outcome.")
        return {"success": True, "message": msg, "effects": {"energy": -5}}

    def _apply_custom_result(self, agent: Agent, action_type: str, result: dict, tick: int) -> dict:
        effects = result.get("effects", {})

        if "hunger" in effects:
            agent.modify_hunger(effects["hunger"])
        if "energy" in effects:
            agent.modify_energy(effects["energy"])
        if "life" in effects:
            agent.modify_life(effects["life"])

        msg = f"{agent.name} performed '{action_type}': {result.get('message', 'OK')}."
        self._log(tick, msg)
        agent.add_memory(
            f"I performed '{action_type}'. Result: {result.get('message', 'OK')}. "
            f"Stats → Life:{agent.life}, Hunger:{agent.hunger}, Energy:{agent.energy}."
        )
        return {"success": result.get("success", True), "message": msg, "effects": effects}

    # --- LLM Calls ---

    def _validate_innovation(self, agent: Agent, action_name: str, description: str, tick: int = 0) -> dict:
        """Use the oracle LLM to validate whether an innovation is reasonable."""
        prompt = f"""An agent named {agent.name} wants to invent a new action called "{action_name}".
Description: "{description}"

The agent is at position ({agent.x}, {agent.y}) on a tile of type "{self.world.get_tile(agent.x, agent.y)}".
The agent's stats: Life={agent.life}, Hunger={agent.hunger}, Energy={agent.energy}.

The world is a primitive survival setting (think early human civilization).
Is this innovation reasonable and feasible given the context?

Respond with JSON: {{"approved": true/false, "reason": "explanation"}}"""

        system = "You are the Oracle of a survival simulation world. You judge whether new actions invented by agents are reasonable. Be fair but realistic. Simple survival innovations (crafting tools, building shelter, gathering) are usually approved. Impossible or magical actions should be rejected."

        result = self.llm.generate_json(prompt, system_prompt=system, temperature=0.3)

        if self.sim_logger and self.llm.last_call:
            lc = self.llm.last_call
            self.sim_logger.log_oracle_llm_call(
                tick=tick, context=f"Validate innovation '{action_name}' by {agent.name}",
                system_prompt=lc.get("system_prompt", ""),
                user_prompt=lc.get("user_prompt", ""),
                raw_response=lc.get("raw_response", ""),
                parsed_result=result,
            )

        if result and "approved" in result:
            return result
        return {"approved": True, "reason": "Oracle could not decide, defaulting to approved."}

    def _oracle_judge_custom_action(self, agent: Agent, action: dict, description: str, tick: int = 0) -> Optional[dict]:
        """Use the LLM to determine the outcome of a custom action."""
        action_type = action.get("action")
        tile = self.world.get_tile(agent.x, agent.y)

        # Include relevant precedents
        relevant_precedents = {k: v for k, v in self.precedents.items()
                               if action_type in k and "effects" in v}

        prompt = f"""Agent "{agent.name}" performs the action "{action_type}" (description: {description}).
Context:
- Position: ({agent.x}, {agent.y}), Tile: {tile}
- Stats: Life={agent.life}, Hunger={agent.hunger}, Energy={agent.energy}
- Action params: {action}
- Previous precedents for similar actions: {relevant_precedents if relevant_precedents else 'None yet'}

Determine the outcome. Consider:
1. What physically happens?
2. How does it affect the agent's stats (hunger, energy, life)?
3. Is there any resource gained or lost?

Respond with JSON:
{{
    "success": true/false,
    "message": "what happened",
    "effects": {{
        "hunger": <integer change, negative=less hungry>,
        "energy": <integer change, negative=spent>,
        "life": <integer change, 0 if not affected>
    }}
}}"""

        system = """You are the Oracle of a survival simulation. You determine outcomes of actions fairly and consistently.
Effects should be reasonable: small actions have small effects (-5 to -10 energy), eating reduces hunger by 15-25, dangerous actions may cost life.
Be deterministic: similar actions in similar contexts should produce similar results."""

        result = self.llm.generate_json(prompt, system_prompt=system, temperature=0.3)

        if self.sim_logger and self.llm.last_call:
            lc = self.llm.last_call
            self.sim_logger.log_oracle_llm_call(
                tick=tick, context=f"Judge custom action '{action_type}' by {agent.name}",
                system_prompt=lc.get("system_prompt", ""),
                user_prompt=lc.get("user_prompt", ""),
                raw_response=lc.get("raw_response", ""),
                parsed_result=result,
            )

        return result

    def _get_fruit_effect(self, tick: int = 0) -> int:
        """Return how much a fruit reduces hunger (consistent)."""
        key = "fruit_hunger_reduction"
        if key in self.precedents:
            return self.precedents[key]["value"]

        # First time: establish the value
        value = 20  # Deterministic base value
        if self.llm:
            prompt = """A human eats a fruit from a tree in a survival world. How much should it reduce their hunger?
The hunger scale is 0-100 where 0=not hungry and 100=starving.
Respond with JSON: {"value": <integer between 10 and 30>}"""
            result = self.llm.generate_json(prompt, temperature=0.2)
            if self.sim_logger and self.llm.last_call:
                lc = self.llm.last_call
                self.sim_logger.log_oracle_llm_call(
                    tick=tick, context="Determine fruit hunger reduction",
                    system_prompt=lc.get("system_prompt", ""),
                    user_prompt=lc.get("user_prompt", ""),
                    raw_response=lc.get("raw_response", ""),
                    parsed_result=result,
                )
            if result and "value" in result:
                value = max(10, min(30, int(result["value"])))

        self.precedents[key] = {"value": value}
        logger.info(f"Oracle established: eating fruit reduces hunger by {value} points.")
        return value

    # --- Logging ---

    def _log(self, tick: int, message: str):
        entry = f"[Tick {tick:04d}] {message}"
        self.world_log.append(entry)
        logger.info(entry)

    def get_recent_log(self, n: int = 20) -> list[str]:
        return self.world_log[-n:]
