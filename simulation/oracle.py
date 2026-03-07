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
    TILE_RISKS, TILE_REST_BONUS,
    COMMUNICATE_ENERGY_COST, AGENT_VISION_RADIUS, COMMUNICATE_TRUST_DELTA,
    GIVE_ITEM_ENERGY_COST, GIVE_ITEM_TRUST_DELTA,
    TEACH_ENERGY_COST_TEACHER, TEACH_ENERGY_COST_LEARNER, TEACH_TRUST_DELTA,
    BASE_ACTIONS,
)
from simulation.message import IncomingMessage, VALID_INTENTS
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

        # Per-tick state for communicate action
        self.current_tick_agents: list = []
        self._communicated_this_tick: set[str] = set()

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
        elif action_type == "pickup":
            return self._resolve_pickup(agent, tick)
        elif action_type == "communicate":
            return self._resolve_communicate(agent, action, tick)
        elif action_type == "give_item":
            return self._resolve_give_item(agent, action, tick)
        elif action_type == "teach":
            return self._resolve_teach(agent, action, tick)
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
            f"Tile types: land (open ground), tree (scattered trees with fruit), sand (beach or shoreline), "
            f"forest (dense forest with mushrooms), mountain (steep rocky peaks), cave (underground cavern), "
            f"river (flowing water channel of varying strength), water (deep lake or ocean — impassable).\n"
            f"Can a human physically attempt to enter this terrain? "
            f"If the terrain is dangerous, estimate life_damage (integer 0–20; 0 = safe). "
            f"River crossings may have current-based damage. Mountains are exhausting but not directly lethal.\n"
            f"Respond with JSON: {{\"possible\": true/false, \"reason\": \"brief explanation\", \"life_damage\": 0}}"
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

        # Apply Oracle-determined life damage (e.g., river current); clamp to [0, 20]
        life_damage = max(0, round(float(judgment.get("life_damage", 0) or 0)))
        if life_damage > 0:
            actual_damage = int(life_damage)
            agent.modify_life(-actual_damage)
            msg += f" Took {actual_damage} damage crossing {tile_type}!"

        # Apply hardcoded extra energy cost for exhausting terrain
        risk = TILE_RISKS.get(tile_type, {})
        extra_energy = risk.get("energy_cost_add", 0)
        if extra_energy > 0:
            agent.modify_energy(-extra_energy)
            cost += extra_energy

        self._log(tick, msg)
        memory_parts = [f"I moved {direction} to ({new_x},{new_y}). Tile: {tile_type}. Energy: {agent.energy}."]
        if life_damage > 0:
            memory_parts.append(f"The {tile_type} crossing cost me {actual_damage} life!")
        agent.add_memory(" ".join(memory_parts))

        effects = {"energy": -cost}
        if life_damage > 0:
            effects["life"] = -actual_damage
        return {"success": True, "message": msg, "effects": effects}

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

        # Collect non-fruit resources nearby so the agent can reason about innovating
        nearby_other = {
            self.world.get_resource(x, y)["type"]
            for (x, y) in positions_to_check
            if self.world.get_resource(x, y) and self.world.get_resource(x, y)["type"] != "fruit"
        }
        if nearby_other:
            resource_hint = ", ".join(sorted(nearby_other))
            msg = f"{agent.name} tried to eat but found no fruit nearby (nearby: {resource_hint})."
            self._log(tick, msg)
            agent.add_memory(
                f"I tried to eat but found no fruit. Nearby resources: {resource_hint}. "
                f"I might need to innovate a new action to use them."
            )
        else:
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
        tile = self.world.get_tile(agent.x, agent.y)
        bonus = TILE_REST_BONUS.get(tile, {}).get("energy_add", 0)
        total_recovery = ENERGY_RECOVERY_REST + bonus
        agent.modify_energy(total_recovery)
        if bonus > 0:
            msg = f"{agent.name} rested in a {tile}. Energy +{total_recovery} (+{bonus} shelter bonus) → {agent.energy}."
            agent.add_memory(f"I rested in a {tile} and recovered {total_recovery} energy ({bonus} bonus from shelter). Energy: {agent.energy}.")
        else:
            msg = f"{agent.name} rested. Energy +{ENERGY_RECOVERY_REST} → {agent.energy}."
            agent.add_memory(f"I rested and recovered energy. Energy: {agent.energy}.")
        self._log(tick, msg)
        return {"success": True, "message": msg, "effects": {"energy": total_recovery}}

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

            # Check item prerequisites (inventory)
            required_items = requires.get("items")
            if isinstance(required_items, dict):
                for item, qty in required_items.items():
                    try:
                        qty_int = int(qty)
                    except (ValueError, TypeError):
                        qty_int = 1  # safe fallback: treat malformed qty as requiring 1
                    if not agent.inventory.has(item, qty_int):
                        msg = (
                            f"{agent.name} cannot innovate '{new_action_name}': "
                            f"requires {qty_int}x {item} in inventory "
                            f"(has {agent.inventory.items.get(item, 0)})."
                        )
                        self._log(tick, msg)
                        agent.add_memory(
                            f"I tried to innovate '{new_action_name}' but I need "
                            f"{qty_int}x {item} (I have {agent.inventory.items.get(item, 0)})."
                        )
                        return {"success": False, "message": msg, "effects": {}}

        # Ask the oracle LLM to validate if the innovation makes sense
        category = "SURVIVAL"
        _aggressive = False
        _trust_impact = None
        if self.llm:
            validation = self._validate_innovation(
                agent, new_action_name, description, tick,
                produces=action.get("produces"),
            )
            if not validation["approved"]:
                msg = f"{agent.name} tried to innovate '{new_action_name}' but the world doesn't allow it: {validation['reason']}."
                self._log(tick, msg)
                agent.add_memory(f"I tried to create the action '{new_action_name}' but it didn't work: {validation['reason']}.")
                return {"success": False, "message": msg, "effects": {}}
            category = validation.get("category", "SURVIVAL")
            _aggressive = validation.get("aggressive", False)
            _trust_impact = float(validation.get("trust_impact", 0.2)) if _aggressive else None

        # Approve innovation
        agent.actions.append(new_action_name)
        agent.modify_energy(-ENERGY_COST_INNOVATE)

        # Register the new action as a precedent
        precedent_data = {
            "creator": agent.name,
            "description": description,
            "tick_created": tick,
            "category": category,
        }
        # Store requires + produces so _resolve_custom_action can handle crafting
        if isinstance(requires, dict):
            precedent_data["requires"] = requires
        produces = action.get("produces")
        if isinstance(produces, dict) and produces:
            precedent_data["produces"] = produces
        # Store aggression metadata for trust damage on execution
        if self.llm and _aggressive:
            precedent_data["aggressive"] = True
            precedent_data["trust_impact"] = _trust_impact
        self.precedents[f"innovation:{new_action_name}"] = precedent_data

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

    def _resolve_pickup(self, agent: Agent, tick: int) -> dict:
        """Agent picks up 1 item from their current tile."""
        x, y = agent.x, agent.y
        resource = self.world.get_resource(x, y)

        if not resource or resource.get("quantity", 0) <= 0:
            msg = f"{agent.name} tried to pick up but there's nothing here."
            self._log(tick, msg)
            agent.add_memory("I tried to pick something up but there was nothing on this tile.")
            return {"success": False, "message": msg, "effects": {}}

        if agent.inventory.free_space() <= 0:
            msg = (
                f"{agent.name} tried to pick up but inventory is full "
                f"({agent.inventory.total()}/{agent.inventory.capacity})."
            )
            self._log(tick, msg)
            agent.add_memory(
                f"I tried to pick something up but my inventory is full "
                f"({agent.inventory.total()}/{agent.inventory.capacity})."
            )
            return {"success": False, "message": msg, "effects": {}}

        item_type = resource["type"]
        self.world.consume_resource(x, y, 1)
        agent.inventory.add(item_type, 1)

        total = agent.inventory.total()
        cap = agent.inventory.capacity
        msg = f"{agent.name} picked up 1 {item_type} (inventory: {total}/{cap})."
        self._log(tick, msg)
        agent.add_memory(
            f"I picked up 1 {item_type} from this tile. Inventory: {agent.inventory.to_prompt()}."
        )
        return {"success": True, "message": msg, "effects": {"item_added": item_type}}

    def _resolve_communicate(self, agent: Agent, action: dict, tick: int) -> dict:
        """Agent sends a message to a nearby agent."""
        intent = action.get("intent", "")
        if intent not in VALID_INTENTS:
            return {"success": False, "message": f"Unknown intent '{intent}'.", "effects": {}}

        if agent.name in self._communicated_this_tick:
            return {"success": False, "message": "Already communicated this tick.", "effects": {}}

        if agent.energy < COMMUNICATE_ENERGY_COST:
            return {"success": False, "message": "Not enough energy to communicate.", "effects": {}}

        target_name = action.get("target", "")
        target = next(
            (a for a in self.current_tick_agents if a.name == target_name and a.alive),
            None,
        )
        if target is None:
            return {"success": False, "message": f"{target_name} not found or not alive.", "effects": {}}

        dist = abs(agent.x - target.x) + abs(agent.y - target.y)
        if dist > AGENT_VISION_RADIUS:
            return {"success": False, "message": f"{target_name} is too far away.", "effects": {}}

        message_text = action.get("message", "")
        agent.energy -= COMMUNICATE_ENERGY_COST
        self._communicated_this_tick.add(agent.name)
        target.incoming_messages.append(
            IncomingMessage(sender=agent.name, tick=tick, message=message_text, intent=intent)
        )
        # Trust: sender trusts recipient a little more after reaching out
        agent.update_relationship(target.name, delta=COMMUNICATE_TRUST_DELTA, tick=tick, is_cooperation=True)
        msg = f"Message sent to {target_name}: \"{message_text}\""
        self._log(tick, f"{agent.name} communicated with {target_name}: [{intent}] {message_text}")
        return {"success": True, "message": msg, "effects": {}}

    def _resolve_give_item(self, agent: Agent, action: dict, tick: int) -> dict:
        """Agent gives an item from their inventory to an adjacent agent."""
        target_name = action.get("target", "")
        item = action.get("item", "")
        quantity = int(action.get("quantity", 1))

        target = next(
            (a for a in self.current_tick_agents if a.name == target_name and a.alive),
            None,
        )
        if target is None:
            return {"success": False, "message": f"{target_name} not found or not alive.", "effects": {}}

        dist = abs(agent.x - target.x) + abs(agent.y - target.y)
        if dist > 1:
            return {"success": False, "message": f"{target_name} is not adjacent.", "effects": {}}

        if agent.energy < GIVE_ITEM_ENERGY_COST:
            return {"success": False, "message": "Not enough energy to give item.", "effects": {}}

        if not agent.inventory.has(item, quantity):
            return {"success": False, "message": f"You don't have {quantity}x {item}.", "effects": {}}

        if target.inventory.free_space() < quantity:
            return {"success": False, "message": f"{target_name}'s inventory is full.", "effects": {}}

        agent.inventory.remove(item, quantity)
        target.inventory.add(item, quantity)
        agent.energy -= GIVE_ITEM_ENERGY_COST
        target.update_relationship(agent.name, delta=GIVE_ITEM_TRUST_DELTA, tick=tick, is_cooperation=True)

        agent.add_memory(f"I gave {quantity}x {item} to {target_name}.")
        target.add_memory(f"{agent.name} gave me {quantity}x {item}.")

        msg = f"{agent.name} gave {quantity}x {item} to {target_name}."
        self._log(tick, msg)
        return {"success": True, "message": msg, "effects": {}}

    def _resolve_teach(self, agent: Agent, action: dict, tick: int) -> dict:
        """Teacher passes an innovation to a learner within vision range (DEC-024: no LLM)."""
        target_name = action.get("target", "")
        skill = action.get("skill", "")

        target = next(
            (a for a in self.current_tick_agents if a.name == target_name and a.alive),
            None,
        )
        if target is None:
            return {"success": False, "message": f"{target_name} not found or not alive.", "effects": {}}

        dist = abs(agent.x - target.x) + abs(agent.y - target.y)
        if dist > AGENT_VISION_RADIUS:
            return {"success": False, "message": f"{target_name} is out of teaching range.", "effects": {}}

        if f"innovation:{skill}" not in self.precedents:
            return {"success": False, "message": f"You don't know the skill '{skill}'.", "effects": {}}

        if skill in BASE_ACTIONS:
            return {"success": False, "message": f"'{skill}' is a base action, cannot be taught.", "effects": {}}

        if skill in target.actions:
            return {"success": False, "message": f"{target_name} already knows '{skill}'.", "effects": {}}

        if agent.energy < TEACH_ENERGY_COST_TEACHER:
            return {"success": False, "message": "Not enough energy to teach.", "effects": {}}

        if target.energy < TEACH_ENERGY_COST_LEARNER:
            return {"success": False, "message": f"{target_name} doesn't have enough energy to learn.", "effects": {}}

        agent.energy -= TEACH_ENERGY_COST_TEACHER
        target.energy -= TEACH_ENERGY_COST_LEARNER
        target.actions.append(skill)

        agent.update_relationship(target_name, delta=TEACH_TRUST_DELTA, tick=tick, is_cooperation=True)
        target.update_relationship(agent.name, delta=TEACH_TRUST_DELTA, tick=tick, is_cooperation=True)

        agent.add_memory(f"I taught {target_name} the skill '{skill}'.")
        target.add_memory(f"{agent.name} taught me the skill '{skill}'.")

        msg = f"{agent.name} taught '{skill}' to {target_name}."
        self._log(tick, msg)
        return {"success": True, "message": msg, "effects": {}}

    # --- Innovated (custom) actions ---

    def _resolve_custom_action(self, agent: Agent, action: dict, tick: int) -> dict:
        action_type = action.get("action")
        precedent_key = f"innovation:{action_type}"

        # Look up information about this action
        innovation = self.precedents.get(precedent_key, {})
        description = innovation.get("description", "unknown action")

        # Extract crafting recipe from stored innovation data
        required_items: dict = {}
        stored_requires = innovation.get("requires")
        if isinstance(stored_requires, dict):
            ri = stored_requires.get("items", {})
            if isinstance(ri, dict):
                required_items = ri
        raw_produces = innovation.get("produces")
        produces: dict = raw_produces if isinstance(raw_produces, dict) else {}

        # Fail fast if crafting items are missing — generic message, no item names revealed
        if required_items:
            for item, qty in required_items.items():
                try:
                    qty_int = int(qty)
                except (ValueError, TypeError):
                    qty_int = 1
                if not agent.inventory.has(item, qty_int):
                    msg = f"{agent.name} tried '{action_type}' but lacked the required materials."
                    self._log(tick, msg)
                    agent.add_memory(
                        f"I tried to '{action_type}' but I was missing materials. "
                        f"I need to gather more resources first."
                    )
                    return {"success": False, "message": msg, "effects": {}}

        # Check if there's already a precedent result for this specific situation
        situation_key = f"custom_action:{action_type}:tile:{self.world.get_tile(agent.x, agent.y)}"
        existing_result = self.precedents.get(situation_key)

        if existing_result:
            result = self._apply_custom_result(agent, action_type, existing_result, tick)
            if result.get("success"):
                result["crafting_event"] = self._apply_crafting_recipe(
                    agent, action_type, required_items, produces, tick
                )
                self._apply_aggressive_trust_damage(agent, action, precedent_key, tick)
            return result

        if not self.llm:
            result = {"success": True, "message": f"{agent.name} performed '{action_type}'.", "effects": {"energy": -5}}
            agent.modify_energy(-5)
            self._log(tick, result["message"])
            result["crafting_event"] = self._apply_crafting_recipe(
                agent, action_type, required_items, produces, tick
            )
            self._apply_aggressive_trust_damage(agent, action, precedent_key, tick)
            return result

        # Ask the oracle to determine the outcome
        oracle_result = self._oracle_judge_custom_action(agent, action, description, tick)

        if oracle_result:
            self.precedents[situation_key] = oracle_result
            result = self._apply_custom_result(agent, action_type, oracle_result, tick)
            if result.get("success"):
                result["crafting_event"] = self._apply_crafting_recipe(
                    agent, action_type, required_items, produces, tick
                )
                self._apply_aggressive_trust_damage(agent, action, precedent_key, tick)
            return result

        # Fallback
        agent.modify_energy(-5)
        msg = f"{agent.name} tried '{action_type}' with uncertain results."
        self._log(tick, msg)
        agent.add_memory(f"I performed '{action_type}' but I'm not sure of the outcome.")
        crafting_event = self._apply_crafting_recipe(agent, action_type, required_items, produces, tick)
        self._apply_aggressive_trust_damage(agent, action, precedent_key, tick)
        return {"success": True, "message": msg, "effects": {"energy": -5}, "crafting_event": crafting_event}

    def _apply_aggressive_trust_damage(self, agent: Agent, action: dict, precedent_key: str, tick: int):
        """If the innovation is marked aggressive, apply trust damage to victim and attacker."""
        precedent = self.precedents.get(precedent_key, {})
        if not precedent.get("aggressive"):
            return
        trust_impact = float(precedent.get("trust_impact", 0.2))
        target_name = action.get("target")
        if not target_name:
            return
        victim = next(
            (a for a in self.current_tick_agents if a.name == target_name and a.alive),
            None,
        )
        if victim:
            victim.update_relationship(agent.name, delta=-trust_impact, tick=tick, is_conflict=True)
            agent.update_relationship(target_name, delta=-trust_impact * 0.5, tick=tick, is_conflict=True)

    def _apply_crafting_recipe(
        self,
        agent: Agent,
        action_type: str,
        required_items: dict,
        produces: dict,
        tick: int,
    ) -> dict:
        """Consume required items and add produced items for a crafting action.

        Pre-condition: caller must have already verified items are available via inventory.has().
        Returns a dict with "consumed" and "produced" keys recording what actually changed.
        """
        consumed: dict[str, int] = {}
        produced: dict[str, int] = {}

        # Consume materials
        for item, qty in required_items.items():
            try:
                qty_int = int(qty)
            except (ValueError, TypeError):
                qty_int = 1
            removed = agent.inventory.remove(item, qty_int)
            if removed:
                consumed[item] = qty_int
            else:
                msg = f"{agent.name} lost track of {qty_int}x {item} during '{action_type}' (inventory inconsistency)."
                self._log(tick, msg)

        # Produce items
        for item, qty in produces.items():
            try:
                qty_int = int(qty)
            except (ValueError, TypeError):
                qty_int = 1
            added = agent.inventory.add(item, qty_int)
            if added > 0:
                produced[item] = added
                agent.add_memory(
                    f"I crafted {added}x {item} via '{action_type}'. "
                    f"Inventory: {agent.inventory.to_prompt()}."
                )
            else:
                msg = f"{agent.name} crafted '{action_type}' but inventory is full — {item} was lost."
                self._log(tick, msg)
                agent.add_memory(
                    f"I crafted '{action_type}' but my inventory is full. I lost the {item} I made."
                )

        return {"consumed": consumed, "produced": produced}

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

    def _validate_innovation(self, agent: Agent, action_name: str, description: str, tick: int = 0, produces: dict | None = None) -> dict:
        """Use the oracle LLM to validate whether an innovation is reasonable."""
        existing = ", ".join(f'"{a}"' for a in agent.actions)
        produces_text = ""
        if isinstance(produces, dict) and produces:
            produces_text = (
                f'\nThe agent claims this action produces: {produces}. '
                f'Is it physically plausible to produce these items from the declared inputs?'
            )
        prompt = f"""An agent named {agent.name} wants to invent a new action called "{action_name}".
Description: "{description}"

The agent is at position ({agent.x}, {agent.y}) on a tile of type "{self.world.get_tile(agent.x, agent.y)}".
The agent's stats: Life={agent.life}, Hunger={agent.hunger}, Energy={agent.energy}.
The agent already knows these actions: {existing}.

The world is a primitive survival setting (think early human civilization).
Is this innovation reasonable, feasible, and meaningfully different from existing actions?{produces_text}

Respond with JSON: {{"approved": true/false, "reason": "explanation", "category": "SURVIVAL|CRAFTING|EXPLORATION|SOCIAL"}}
If this action involves aggression toward another agent (stealing, attacking, threatening), also include:
  "aggressive": true, "trust_impact": <float 0.05-0.5 based on severity>
Otherwise omit both fields."""

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
