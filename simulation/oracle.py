"""
Oracle: validates and resolves agent actions.
Maintains a decision memory for determinism (consistency).
"""

import json
import logging
from pathlib import Path
from typing import Optional

from simulation.config import (
    ENERGY_COST_MOVE, ENERGY_COST_EAT, ENERGY_COST_INNOVATE,
    ENERGY_RECOVERY_REST, INNOVATION_EFFECT_BOUNDS,
)
from simulation.llm_client import LLMClient
from simulation.world import World
from simulation.agent import Agent
from simulation import prompt_loader

logger = logging.getLogger(__name__)

DIRECTION_DELTAS = {
    "north":     (0, -1),
    "south":     (0,  1),
    "east":      (1,  0),
    "west":      (-1, 0),
    "northeast": (1, -1),
    "northwest": (-1, -1),
    "southeast": (1,  1),
    "southwest": (-1, 1),
    "north-east": (1, -1),
    "north-west": (-1, -1),
    "south-east": (1,  1),
    "south-west": (-1, 1),
}


class Oracle:
    """
    The oracle is the world's arbiter.
    Validates actions, determines outcomes, and maintains consistency.
    """

    def __init__(self, world: World, llm: Optional[LLMClient] = None, sim_logger=None,
                 day_cycle=None):
        self.world = world
        self.llm = llm
        self.sim_logger = sim_logger
        self.day_cycle = day_cycle  # Optional DayCycle for time-based energy costs

        # Oracle memory: stores precedents for determinism
        # Key: descriptive string of the situation -> result
        self.precedents: dict[str, dict] = {}

        # Log of everything that has happened in the world
        self.world_log: list[str] = []

    def load_precedents(self, filepath: str) -> None:
        """Load precedents from a JSON file and merge into self.precedents.

        Silently skips if the file does not exist.
        Logs a warning and leaves existing precedents unchanged if the file is corrupt.
        """
        path = Path(filepath)
        if not path.exists():
            logger.debug("No precedent file at %s, starting fresh.", filepath)
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            loaded = data.get("precedents", {})
            self.precedents.update(loaded)
            logger.info("Loaded %d precedents from %s", len(loaded), filepath)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load precedents from %s: %s", filepath, exc)

    def save_precedents(
        self, filepath: str, tick: int = 0, world_seed: Optional[int] = None
    ) -> None:
        """Save current precedents to a JSON file.

        Creates parent directories as needed.
        Logs a warning on I/O or serialisation failure; does not raise.
        """
        path = Path(filepath)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "world_seed": world_seed,
                "saved_at_tick": tick,
                "precedents": self.precedents,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("Saved %d precedents to %s", len(self.precedents), filepath)
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Could not save precedents to %s: %s", filepath, exc)

    def _apply_energy_cost(self, agent: Agent, base_cost: int, tick: int) -> int:
        """Apply an energy cost with the day/night multiplier. Returns actual cost spent."""
        multiplier = self.day_cycle.get_energy_multiplier(tick) if self.day_cycle else 1.0
        actual_cost = round(base_cost * multiplier)
        agent.modify_energy(-actual_cost)
        return actual_cost

    def _clamp_innovation_effects(self, effects: dict) -> dict:
        """Clamp custom-action stat deltas to the configured safe bounds."""
        clamped = dict(effects)
        for stat, (lo, hi) in INNOVATION_EFFECT_BOUNDS.items():
            if stat in clamped:
                clamped[stat] = max(lo, min(hi, int(clamped[stat])))
        return clamped

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

    # --- Physical reflection ---

    def _oracle_reflect_physical(self, situation_key: str, prompt: str, tick: int) -> dict:
        """
        Ask the Oracle if a physical action is possible.
        Checks precedent first. If not found, consults LLM. Always caches result.
        Returns: {"possible": bool, "reason": str}
        """
        if situation_key in self.precedents:
            return self.precedents[situation_key]

        default = {"possible": True, "reason": "Default: allowed."}

        if self.llm:
            system = prompt_loader.load("oracle/physical_system")
            result = self.llm.generate_json(prompt, system_prompt=system, temperature=0.2)
            if self.sim_logger and self.llm.last_call:
                lc = self.llm.last_call
                self.sim_logger.log_oracle_llm_call(
                    tick=tick, context=f"Physical reflection: {situation_key}",
                    system_prompt=lc.get("system_prompt", ""),
                    user_prompt=lc.get("user_prompt", ""),
                    raw_response=lc.get("raw_response", ""),
                    parsed_result=result,
                )
            if result and "possible" in result:
                self.precedents[situation_key] = result
                logger.info(f"Oracle established physical rule: [{situation_key}] → {result}")
                return result

        self.precedents[situation_key] = default
        return default

    # --- Base actions ---

    def _resolve_move(self, agent: Agent, action: dict, tick: int) -> dict:
        direction = action.get("direction", "north").lower()
        delta = DIRECTION_DELTAS.get(direction)
        if delta is None:
            return {"success": False, "message": f"Unknown direction: {direction}", "effects": {}}

        dx, dy = delta
        new_x, new_y = agent.x + dx, agent.y + dy

        # Hard boundary check (edge of the simulated world)
        tile_type = self.world.get_tile(new_x, new_y)
        if tile_type is None:
            msg = f"{agent.name} cannot move {direction}: out of bounds."
            self._log(tick, msg)
            agent.add_memory(f"I tried to move {direction} but hit the world's edge.")
            return {"success": False, "message": msg, "effects": {}}

        # Oracle reflects on whether this tile type is traversable
        situation_key = f"physical:traversal:tile:{tile_type}"
        reflection_prompt = (
            f"A human in a primitive survival world tries to enter a \"{tile_type}\" tile.\n"
            f"Tile types in this world: \"land\" (open ground), \"tree\" (forested area), "
            f"\"water\" (river or lake).\n"
            f"Can a human physically attempt to enter this terrain? (dangerous is not the same as impossible)\n"
            f"Respond with JSON: {{\"possible\": true/false, \"reason\": \"brief explanation\"}}"
        )
        judgment = self._oracle_reflect_physical(situation_key, reflection_prompt, tick)

        if not judgment["possible"]:
            reason = judgment.get("reason", f"cannot walk on {tile_type}")
            msg = f"{agent.name} cannot move {direction}: {reason}."
            self._log(tick, msg)
            agent.add_memory(f"I tried to move {direction} but couldn't: {reason}.")
            return {"success": False, "message": msg, "effects": {}}

        # Move succeeds
        agent.x, agent.y = new_x, new_y
        cost = self._apply_energy_cost(agent, ENERGY_COST_MOVE, tick)
        msg = f"{agent.name} moved {direction} → ({new_x},{new_y}) [tile: {tile_type}]."
        self._log(tick, msg)
        agent.add_memory(
            f"I moved {direction} to ({new_x},{new_y}). There is {tile_type}. Energy: {agent.energy}."
        )
        return {"success": True, "message": msg, "effects": {"energy": -cost}}

    def _resolve_eat(self, agent: Agent, action: dict, tick: int) -> dict:
        situation_key = "physical:eat:fruit"
        if situation_key not in self.precedents:
            reflection_prompt = (
                "In a primitive survival world, a human picks and eats a fruit from a nearby tree. "
                "Is this physically possible? "
                "Respond with JSON: {\"possible\": true, \"reason\": \"brief explanation\"}"
            )
            self._oracle_reflect_physical(situation_key, reflection_prompt, tick)

        # Food-presence check is pure world state (not a physical law)
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
                    hunger_reduction = self._get_fruit_effect(tick)
                    agent.modify_hunger(-hunger_reduction)
                    cost = self._apply_energy_cost(agent, ENERGY_COST_EAT, tick)
                    msg = f"{agent.name} ate fruit at ({x},{y}). Hunger -{hunger_reduction} → {agent.hunger}."
                    self._log(tick, msg)
                    agent.add_memory(
                        f"I ate a fruit. My hunger decreased by {hunger_reduction} to {agent.hunger}. Energy: {agent.energy}."
                    )
                    return {"success": True, "message": msg, "effects": {"hunger": -hunger_reduction, "energy": -cost}}

        msg = f"{agent.name} tried to eat but there's no food nearby."
        self._log(tick, msg)
        agent.add_memory("I tried to eat but couldn't find food within reach.")
        return {"success": False, "message": msg, "effects": {}}

    def _resolve_rest(self, agent: Agent, action: dict, tick: int) -> dict:
        situation_key = "physical:rest"
        if situation_key not in self.precedents:
            reflection_prompt = (
                "In a primitive survival world, a human chooses to stop and rest. "
                "Is resting physically possible regardless of terrain? "
                "Respond with JSON: {\"possible\": true, \"reason\": \"brief explanation\"}"
            )
            self._oracle_reflect_physical(situation_key, reflection_prompt, tick)

        # Rest is always possible (precedent establishes this)
        agent.modify_energy(ENERGY_RECOVERY_REST)
        msg = f"{agent.name} rested. Energy +{ENERGY_RECOVERY_REST} → {agent.energy}."
        self._log(tick, msg)
        agent.add_memory(f"I rested and recovered energy. Energy: {agent.energy}.")
        return {"success": True, "message": msg, "effects": {"energy": ENERGY_RECOVERY_REST}}

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

        # Validate prerequisites declared by the agent (no LLM call needed)
        requires = action.get("requires")
        if isinstance(requires, dict):
            required_tile = requires.get("tile")
            if required_tile:
                current_tile = self.world.get_tile(agent.x, agent.y)
                if current_tile != required_tile:
                    msg = (
                        f"{agent.name} cannot innovate '{new_action_name}': "
                        f"requires {required_tile} tile but is on {current_tile}."
                    )
                    self._log(tick, msg)
                    agent.add_memory(
                        f"I tried to innovate '{new_action_name}' but I need to be on {required_tile} (I'm on {current_tile})."
                    )
                    return {"success": False, "message": msg, "effects": {}}

            min_energy = requires.get("min_energy")
            if min_energy is not None and agent.energy < int(min_energy):
                msg = (
                    f"{agent.name} cannot innovate '{new_action_name}': "
                    f"requires {min_energy} energy but has {agent.energy}."
                )
                self._log(tick, msg)
                agent.add_memory(
                    f"I tried to innovate '{new_action_name}' but I need at least {min_energy} energy."
                )
                return {"success": False, "message": msg, "effects": {}}

        # Ask the oracle LLM to validate if the innovation makes sense
        category = "SURVIVAL"
        if self.llm:
            validation = self._validate_innovation(agent, new_action_name, description, tick)
            if not validation["approved"]:
                msg = f"{agent.name} tried to innovate '{new_action_name}' but the world doesn't allow it: {validation['reason']}."
                self._log(tick, msg)
                agent.add_memory(f"I tried to create the action '{new_action_name}' but it didn't work: {validation['reason']}.")
                return {"success": False, "message": msg, "effects": {}}
            category = validation.get("category", "SURVIVAL")

        # Approve innovation
        agent.actions.append(new_action_name)
        agent.modify_energy(-ENERGY_COST_INNOVATE)

        # Register the new action as a precedent
        self.precedents[f"innovation:{new_action_name}"] = {
            "creator": agent.name,
            "description": description,
            "tick_created": tick,
            "category": category,
        }

        msg = f"🆕 {agent.name} innovated '{new_action_name}' [{category}]: {description}."
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
        existing = ", ".join(f'"{a}"' for a in agent.actions)
        prompt = f"""An agent named {agent.name} wants to invent a new action called "{action_name}".
Description: "{description}"

The agent is at position ({agent.x}, {agent.y}) on a tile of type "{self.world.get_tile(agent.x, agent.y)}".
The agent's stats: Life={agent.life}, Hunger={agent.hunger}, Energy={agent.energy}.
The agent already knows these actions: {existing}.

The world is a primitive survival setting (think early human civilization).
Is this innovation reasonable, feasible, and meaningfully different from existing actions?

Respond with JSON: {{"approved": true/false, "reason": "explanation", "category": "SURVIVAL|CRAFTING|EXPLORATION|SOCIAL"}}"""

        system = prompt_loader.load("oracle/innovation_system")

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
        return {"approved": True, "reason": "Oracle could not decide, defaulting to approved.", "category": "SURVIVAL"}

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

        system = prompt_loader.load("oracle/custom_action_system")

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

        if result and "effects" in result:
            result["effects"] = self._clamp_innovation_effects(result["effects"])

        return result

    def _get_fruit_effect(self, tick: int = 0) -> int:
        """Return how much a fruit reduces hunger (consistent)."""
        key = "fruit_hunger_reduction"
        if key in self.precedents:
            return self.precedents[key]["value"]

        # First time: establish the value
        value = 20  # Deterministic base value
        if self.llm:
            prompt = prompt_loader.load("oracle/fruit_effect")
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
