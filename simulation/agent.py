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
    ENERGY_COST_MOVE, ENERGY_COST_EAT, ENERGY_COST_INNOVATE, ENERGY_COST_PICKUP,
    ENERGY_RECOVERY_REST, ENERGY_LOW_THRESHOLD, ENERGY_DAMAGE_PER_TICK,
    BASE_ACTIONS, AGENT_VISION_RADIUS, AGENT_INVENTORY_CAPACITY,
)
from simulation.llm_client import LLMClient
from simulation.memory import Memory
from simulation.inventory import Inventory
from simulation.personality import Personality
from simulation import prompt_loader
from simulation.message import IncomingMessage

logger = logging.getLogger(__name__)

# Mapping from tile type to ASCII character for the 7x7 vision grid.
_TILE_CHARS: dict[str, object] = {
    "tree":     lambda tile: "F" if "resource" in tile else "t",
    "water":    lambda _: "W",
    "sand":     lambda _: "S",
    "forest":   lambda _: "f",
    "mountain": lambda _: "M",
    "cave":     lambda _: "C",
    "river":    lambda _: "~",
    "land":     lambda _: ".",
}

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

        # Dual memory system (episodic + semantic)
        self.memory_system = Memory()

        # Inventory (quantity-based, max AGENT_INVENTORY_CAPACITY total items)
        self.inventory = Inventory(capacity=AGENT_INVENTORY_CAPACITY)

        # Incoming messages from other agents (cleared after decide_action each tick)
        self.incoming_messages: list[IncomingMessage] = []

        # Personality traits (injected into system prompt)
        self.personality = Personality.random()

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

        # If energy is completely depleted, life decreases
        if self.energy <= 0:
            self.life = max(0, self.life - ENERGY_DAMAGE_PER_TICK)
            self.add_memory(f"I'm completely exhausted (energy=0). My life drops to {self.life}.")

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
            "pickup": ENERGY_COST_PICKUP,
            "innovate": ENERGY_COST_INNOVATE,
        }
        cost = costs.get(action, 5)  # innovated actions: default cost 5
        return self.energy >= cost

    # --- Memory ---

    def add_memory(self, entry: str):
        """Add an entry to episodic memory."""
        self.memory_system.add_episode(entry)

    def get_recent_memory(self) -> str:
        """Return formatted memory for the decision prompt."""
        return self.memory_system.to_prompt()

    @property
    def memory(self) -> list[str]:
        """Backward-compatible access to all memory entries."""
        return self.memory_system.all_entries()

    def nearby_agents_prompt(self, visible_agents: list[tuple]) -> str:
        """
        Format nearby agents for the decision prompt.
        Returns empty string if no agents are visible (omits the section entirely).
        Uses fuzzy stats to avoid revealing exact numbers.
        """
        if not visible_agents:
            return ""

        lines = ["NEARBY AGENTS:"]
        for other, distance in visible_agents:
            status_parts = []
            if other.hunger > 50:
                status_parts.append("looks hungry")
            if other.energy < 30:
                status_parts.append("looks tired")
            if other.life < 50:
                status_parts.append("looks hurt")
            if other.inventory.items:
                status_parts.append("carrying items")
            status = ". ".join(status_parts).capitalize() if status_parts else "Looks healthy"
            tile_word = "tile" if distance == 1 else "tiles"
            lines.append(
                f"- {other.name} @ ({other.x},{other.y}), {distance} {tile_word} away. {status}."
            )
        return "\n".join(lines)

    def get_messages_prompt(self) -> str:
        if not self.incoming_messages:
            return ""
        lines = ["INCOMING MESSAGES:"]
        for msg in self.incoming_messages:
            lines.append(f'- {msg.sender} (tick {msg.tick}): "{msg.message}" [{msg.intent}]')
        return "\n".join(lines)

    # --- Decision making with LLM ---

    def decide_action(self, nearby_tiles: list[dict], tick: int,
                      time_description: str = "",
                      nearby_agents: list | None = None) -> dict:
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
        user_prompt = self._build_decision_prompt(nearby_tiles, tick, time_description,
                                                  nearby_agents=nearby_agents or [])

        result = self.llm.generate_json(user_prompt, system_prompt=system_prompt)
        
        logger.debug(f"[{self.name}] LLM raw response: {result}")
        
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

    def _build_ascii_grid(self, nearby_tiles: list[dict]) -> str:
        """Build a 7x7 ASCII grid centered on the agent."""
        tile_map = {(t["x"], t["y"]): t for t in nearby_tiles}
        radius = AGENT_VISION_RADIUS
        rows = []
        for dy in range(-radius, radius + 1):  # -3 (north) to +3 (south)
            row_chars = []
            for dx in range(-radius, radius + 1):  # -3 (west) to +3 (east)
                nx, ny = self.x + dx, self.y + dy
                if dx == 0 and dy == 0:
                    row_chars.append("@")
                elif (nx, ny) in tile_map:
                    t = tile_map[(nx, ny)]
                    tile_type = t["tile"]
                    char_fn = _TILE_CHARS.get(tile_type, lambda _: ".")
                    row_chars.append(char_fn(t))
                else:
                    row_chars.append("#")
            rows.append(" ".join(row_chars))
        return "\n".join(rows)

    def _build_resource_hints(self, nearby_tiles: list[dict]) -> str:
        """Pre-compute directional hints so the model never has to do coordinate math."""
        resource_tiles = [t for t in nearby_tiles if "resource" in t]
        if not resource_tiles:
            return "No resources visible."
        resource_tiles.sort(key=lambda t: t["distance"])
        hints = []
        for t in resource_tiles:
            dx = t["x"] - self.x
            dy = t["y"] - self.y  # negative dy = north
            resource_type = t["resource"]["type"]
            qty = t["resource"]["quantity"]
            dist = t["distance"]
            parts = []
            if dy < 0:
                parts.append("NORTH")
            elif dy > 0:
                parts.append("SOUTH")
            if dx > 0:
                parts.append("EAST")
            elif dx < 0:
                parts.append("WEST")
            direction = "-".join(parts) if parts else "HERE"
            tile_word = "tile" if dist == 1 else "tiles"
            hints.append(f"- {resource_type} {dist} {tile_word} {direction} (qty: {qty})")
        return "\n".join(hints)

    def _build_system_prompt(self) -> str:
        return prompt_loader.render(
            "agent/system",
            name=self.name,
            actions=", ".join(self.actions),
            personality_description=self.personality.to_prompt(),
        )

    def _build_decision_prompt(self, nearby_tiles: list[dict], tick: int,
                               time_description: str = "",
                               nearby_agents: list | None = None) -> str:
        ascii_grid = self._build_ascii_grid(nearby_tiles)
        # Current tile type — shown to agent so it can write valid requires.tile in innovations
        _current_tile = next(
            (t["tile"] for t in nearby_tiles if t["x"] == self.x and t["y"] == self.y),
            "land",
        )
        current_tile_info = f"[Tile: {_current_tile}]"
        resource_hints = self._build_resource_hints(nearby_tiles)
        memory_text = self.get_recent_memory()

        if self.energy <= 0:
            status_effects = prompt_loader.load("agent/energy_critical")
        elif self.energy <= ENERGY_LOW_THRESHOLD:
            status_effects = prompt_loader.load("agent/energy_low")
        else:
            status_effects = ""

        inventory_info = self.inventory.to_prompt()  # empty string if empty
        nearby_agents_text = self.nearby_agents_prompt(nearby_agents or [])

        return prompt_loader.render(
            "agent/decision",
            tick=tick,
            life=self.life,
            max_life=AGENT_MAX_LIFE,
            hunger=self.hunger,
            max_hunger=AGENT_MAX_HUNGER,
            hunger_threshold=HUNGER_DAMAGE_THRESHOLD,
            energy=self.energy,
            max_energy=AGENT_MAX_ENERGY,
            ascii_grid=ascii_grid,
            resource_hints=resource_hints,
            memory_text=memory_text,
            status_effects=status_effects,
            time_info=time_description,
            inventory_info=inventory_info,
            current_tile_info=current_tile_info,
            nearby_agents=nearby_agents_text,
        )

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
            "memory_entries": self.memory_system.total_entries,
            "memory_episodic": len(self.memory_system.episodic),
            "memory_semantic": len(self.memory_system.semantic),
            "inventory": self.inventory.to_dict(),
        }

    def __repr__(self):
        status = "💀" if not self.alive else "💚"
        return f"{status} {self.name} @({self.x},{self.y}) [HP:{self.life} HNG:{self.hunger} ENR:{self.energy}]"
