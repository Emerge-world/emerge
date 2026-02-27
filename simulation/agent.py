"""
Human agent controlled by LLM.
Has life, hunger, energy, memory, and an action repertoire.
"""

import logging
from typing import Optional

from simulation.config import (
    AGENT_MAX_LIFE, AGENT_MAX_HUNGER, AGENT_MAX_ENERGY,
    AGENT_START_LIFE, AGENT_START_HUNGER, AGENT_START_ENERGY,
    HUNGER_PER_TICK, HUNGER_DAMAGE_THRESHOLD, HUNGER_DAMAGE_PER_TICK,
    ENERGY_COST_MOVE, ENERGY_COST_EAT, ENERGY_COST_INNOVATE,
    ENERGY_RECOVERY_REST,
    BASE_ACTIONS, AGENT_VISION_RADIUS,
)
from simulation.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Agent names
AGENT_NAMES = ["Ada", "Bruno", "Clara", "Dante", "Elena",
               "Felix", "Gaia", "Hugo", "Iris", "Joel"]


class Agent:
    """A human agent in the simulation."""

    _id_counter = 0

    def __init__(self, name: Optional[str] = None, x: int = 0, y: int = 0, llm: Optional[LLMClient] = None):
        Agent._id_counter += 1
        self.id = Agent._id_counter
        self.name = name or AGENT_NAMES[(self.id - 1) % len(AGENT_NAMES)]

        # Position
        self.x = x
        self.y = y

        # Stats
        self.life = AGENT_START_LIFE
        self.hunger = AGENT_START_HUNGER
        self.energy = AGENT_START_ENERGY
        self.alive = True

        # Memory: list of strings recording what has happened
        self.memory: list[str] = []
        self.max_memory = 50  # Last N entries to avoid saturating the prompt

        # Available actions (starts with base actions, can innovate new ones)
        self.actions: list[str] = list(BASE_ACTIONS)

        # LLM
        self.llm = llm

        logger.info(f"Agent '{self.name}' created at ({self.x}, {self.y})")

    # --- Stats management ---

    def apply_tick_effects(self):
        """Passive effects each tick: hunger increases, possible life damage."""
        if not self.alive:
            return

        # Hunger increases
        self.hunger = min(self.hunger + HUNGER_PER_TICK, AGENT_MAX_HUNGER)

        # If hunger exceeds threshold, life decreases
        if self.hunger >= HUNGER_DAMAGE_THRESHOLD:
            self.life = max(0, self.life - HUNGER_DAMAGE_PER_TICK)
            self.add_memory(f"I'm very hungry (hunger={self.hunger}). My life drops to {self.life}.")

        # Check death
        if self.life <= 0:
            self.alive = False
            self.add_memory("I have died.")
            logger.info(f"☠️  Agent '{self.name}' has died.")

    def modify_hunger(self, amount: int):
        """Modify hunger (negative = reduces hunger)."""
        self.hunger = max(0, min(AGENT_MAX_HUNGER, self.hunger + amount))

    def modify_energy(self, amount: int):
        """Modify energy (negative = spend, positive = recover)."""
        self.energy = max(0, min(AGENT_MAX_ENERGY, self.energy + amount))

    def modify_life(self, amount: int):
        """Modify life."""
        self.life = max(0, min(AGENT_MAX_LIFE, self.life + amount))
        if self.life <= 0:
            self.alive = False

    def has_energy_for(self, action: str) -> bool:
        """Check if the agent has enough energy for an action."""
        costs = {
            "move": ENERGY_COST_MOVE,
            "eat": ENERGY_COST_EAT,
            "rest": 0,
            "innovate": ENERGY_COST_INNOVATE,
        }
        cost = costs.get(action, 5)  # innovated actions: default cost 5
        return self.energy >= cost

    # --- Memory ---

    def add_memory(self, entry: str):
        """Add an entry to the memory log."""
        self.memory.append(entry)
        if len(self.memory) > self.max_memory:
            self.memory = self.memory[-self.max_memory:]

    def get_recent_memory(self, n: int = 15) -> str:
        """Return the last N memory entries as text."""
        recent = self.memory[-n:]
        if not recent:
            return "I have no previous memories. I just arrived in the world."
        return "\n".join(f"- {m}" for m in recent)

    # --- Decision making with LLM ---

    def decide_action(self, nearby_tiles: list[dict], tick: int) -> dict:
        """
        Ask the LLM to decide what action to take.
        Returns a dict with the action and its parameters.
        """
        if not self.alive:
            return {"action": "none", "reason": "I am dead"}

        if not self.llm:
            # Fallback without LLM: simple random action
            return self._fallback_decision(nearby_tiles)

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_decision_prompt(nearby_tiles, tick)

        result = self.llm.generate_json(user_prompt, system_prompt=system_prompt)

        # Capture LLM trace for the sim logger (uses the underlying generate() call's last_call)
        llm_trace = dict(self.llm.last_call) if self.llm.last_call else {}

        if result and "action" in result:
            logger.debug(f"[{self.name}] LLM decided: {result}")
            result["_llm_trace"] = llm_trace
            return result
        else:
            logger.warning(f"[{self.name}] LLM did not return a valid action, using fallback")
            fallback = self._fallback_decision(nearby_tiles)
            fallback["_llm_trace"] = llm_trace
            return fallback

    def _build_system_prompt(self) -> str:
        return f"""You are {self.name}, a human trying to survive in a 2D world.
You must choose actions wisely to stay alive. You need to eat to reduce hunger, rest to recover energy, and explore to find resources.

Your current stats:
- Life: {self.life}/{AGENT_MAX_LIFE}
- Hunger: {self.hunger}/{AGENT_MAX_HUNGER} (higher = more hungry, at {HUNGER_DAMAGE_THRESHOLD} you start losing life)
- Energy: {self.energy}/{AGENT_MAX_ENERGY}

Available actions: {', '.join(self.actions)}

Action format - respond with a JSON object:
- move: {{"action": "move", "direction": "north|south|east|west", "reason": "..."}}
- eat: {{"action": "eat", "reason": "..."}} (eat food at current or adjacent tile)
- rest: {{"action": "rest", "reason": "..."}} (recover energy, skip this turn)
- innovate: {{"action": "innovate", "new_action_name": "...", "description": "...", "reason": "..."}} (create a new type of action)
- For any innovated action: {{"action": "<action_name>", "reason": "...", ...extra_params}}

Always respond ONLY with a valid JSON object. Be strategic about survival."""

    def _build_decision_prompt(self, nearby_tiles: list[dict], tick: int) -> str:
        # Summary of nearby tiles
        tile_descriptions = []
        for t in nearby_tiles:
            desc = f"  ({t['x']},{t['y']}): {t['tile']}"
            if "resource" in t:
                desc += f" [resource: {t['resource']['type']}, qty: {t['resource']['quantity']}]"
            if t["x"] == self.x and t["y"] == self.y:
                desc += " ← YOU ARE HERE"
            tile_descriptions.append(desc)

        nearby_text = "\n".join(tile_descriptions[:30])  # Limit to avoid saturation

        memory_text = self.get_recent_memory()

        return f"""TICK {tick} - It's time to decide your next action.

YOUR POSITION: ({self.x}, {self.y})
YOUR STATS: Life={self.life}, Hunger={self.hunger}, Energy={self.energy}

NEARBY TILES (what you can see):
{nearby_text}

YOUR RECENT MEMORY:
{memory_text}

What do you do? Respond with a JSON object."""

    def _fallback_decision(self, nearby_tiles: list[dict]) -> dict:
        """Basic decision without LLM based on simple rules."""
        # If very hungry and food is nearby, eat
        if self.hunger > 40:
            for t in nearby_tiles:
                if "resource" in t and t["distance"] <= 1:
                    return {"action": "eat", "reason": "I'm hungry and there's food nearby"}

        # If low on energy, rest
        if self.energy < 20:
            return {"action": "rest", "reason": "I'm exhausted"}

        # Otherwise, move towards resources
        food_tiles = [t for t in nearby_tiles if "resource" in t and t["distance"] > 0]
        if food_tiles:
            closest = min(food_tiles, key=lambda t: t["distance"])
            dx = closest["x"] - self.x
            dy = closest["y"] - self.y
            if abs(dx) >= abs(dy):
                direction = "east" if dx > 0 else "west"
            else:
                direction = "south" if dy > 0 else "north"
            return {"action": "move", "direction": direction, "reason": "Heading towards food"}

        # Random movement
        import random
        direction = random.choice(["north", "south", "east", "west"])
        return {"action": "move", "direction": direction, "reason": "Exploring the world"}

    # --- Representation ---

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "position": (self.x, self.y),
            "life": self.life,
            "hunger": self.hunger,
            "energy": self.energy,
            "alive": self.alive,
            "actions": self.actions,
            "memory_entries": len(self.memory),
        }

    def __repr__(self):
        status = "💀" if not self.alive else "💚"
        return f"{status} {self.name} @({self.x},{self.y}) [HP:{self.life} HNG:{self.hunger} ENR:{self.energy}]"
