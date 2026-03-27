from __future__ import annotations

import re

from simulation import prompt_loader
from simulation.runtime_policy import AgentRuntimeSettings, MemoryRuntimeSettings


class PromptSurfaceBuilder:
    def __init__(
        self,
        *,
        agent_settings: AgentRuntimeSettings,
        memory_settings: MemoryRuntimeSettings,
    ) -> None:
        self.agent_settings = agent_settings
        self.memory_settings = memory_settings

    def build_executor_system(
        self,
        *,
        name: str,
        actions: list[str],
        personality_description: str,
        action_descriptions: dict[str, str],
    ) -> str:
        return self._normalize(
            prompt_loader.render(
                "agent/system",
                name=name,
                actions=", ".join(actions),
                personality_description=personality_description,
                strategic_capability_reminders=self._strategic_capability_reminders(),
                builtin_action_examples=self._executor_builtin_action_examples(),
                reproduction_action_note=self._reproduction_action_note(actions),
                custom_actions_section=self._custom_actions_section(action_descriptions),
            )
        )

    def _normalize(self, text: str) -> str:
        lines = [line.rstrip() for line in text.splitlines()]
        normalized = "\n".join(lines).strip()
        return re.sub(r"\n{3,}", "\n\n", normalized)

    def _strategic_capability_reminders(self) -> str:
        lines: list[str] = []
        if self.agent_settings.innovation:
            lines.append(
                "- Some useful resources or situations may not be solvable with base actions "
                "alone. When you can see a promising opportunity but lack a way to use it, "
                "inventing a simple new action is valid."
            )
        lines.append(
            "- Repeating the same low-value behavior without progress is usually a sign to "
            "change approach."
        )
        if self.agent_settings.social:
            lines.append(
                "- Surplus energy, low hunger, trusted nearby agents, and useful knowledge can "
                f"create opportunities for {self._long_horizon_options_text()}."
            )
            if self.agent_settings.teach:
                lines.append(
                    "- Teaching, sharing, and protecting useful knowledge can matter even "
                    "when immediate danger is low."
                )
        elif self.agent_settings.reproduction:
            lines.append(
                "- When conditions are favorable, consider choices that help kin or future "
                "generations persist."
            )
        return "\n".join(lines)

    def _long_horizon_options_text(self) -> str:
        options = ["cooperation"]
        if self.agent_settings.teach:
            options.append("teaching")
        if self.agent_settings.reproduction:
            options.append("reproduction")
        if len(options) == 1:
            return options[0]
        if len(options) == 2:
            return f"{options[0]} or {options[1]}"
        return f"{', '.join(options[:-1])}, or {options[-1]}"

    def _executor_builtin_action_examples(self) -> str:
        lines: list[str] = [
            '- move: {"action": "move", "direction": "north|northeast|east|southeast|south|southwest|west|northwest", "reason": "..."}',
            '- eat: {"action": "eat", "reason": "..."} (eat food at current or adjacent tile)',
            '  IMPORTANT: If no food tile is within reach but you have edible food in INVENTORY, you MUST use: {"action": "eat", "item": "<item_name>", "reason": "..."}',
            "  Edible items: fruit, mushroom, water. You cannot eat stone.",
            '- rest: {"action": "rest", "reason": "..."} (recover energy, skip turn)',
            '- pickup: {"action": "pickup", "reason": "..."} (collect 1 item from current tile into inventory)',
            "  IMPORTANT: Only use pickup when the resource is on your current tile. If a resource is visible on another tile, move first.",
            '- drop_item: {"action": "drop_item", "item": "<item_name>", "quantity": 1, "reason": "..."}',
            "  (drop an inventory item onto your current tile; fails if the tile already holds a different resource)",
        ]
        if self.agent_settings.innovation:
            lines.extend(
                [
                    '- innovate: {"action": "innovate", "new_action_name": "...", "description": "...", "reason": "...", "requires": {"tile": "cave|forest|mountain|river|...", "min_energy": <n>, "items": {"stone": 2}}, "produces": {"knife": 1}}',
                    "  (requires and produces are optional. Use requires.tile when the action only makes sense in a specific terrain type. Use produces when your action creates a physical item from materials.)",
                ]
            )
        if self.agent_settings.social:
            lines.extend(
                [
                    '- communicate: {"action": "communicate", "target": "<name>", "message": "<text>", "intent": "<share_info|request_help|warn|trade_offer>", "reason": "..."}',
                    "  (send a message to a nearby visible agent; costs 3 energy; once per tick)",
                    '- give_item: {"action": "give_item", "target": "<name>", "item": "<item_name>", "quantity": 1, "reason": "..."}',
                    "  (give an item from your inventory to an adjacent agent; costs 2 energy)",
                ]
            )
            if self.agent_settings.teach:
                lines.extend(
                    [
                        '- teach: {"action": "teach", "target": "<name>", "skill": "<innovation_name>", "reason": "..."}',
                        "  (teach a visible agent one of your innovations; costs 8 energy for you, 5 for learner)",
                    ]
                )
        if self.agent_settings.item_reflection:
            lines.extend(
                [
                    '- reflect_item_uses: {"action": "reflect_item_uses", "item": "<item_name>", "reason": "..."}',
                    "  (reflect on a held item to discover potential new uses; costs 5 energy; item must be in your inventory)",
                ]
            )
        return "\n".join(lines)

    def _reproduction_action_note(self, actions: list[str]) -> str:
        if not self.agent_settings.reproduction:
            return ""
        _ = actions
        return (
            "- If reproduce appears in Available actions or is described in a hint below, "
            "use the reproduction format provided there."
        )

    def _custom_actions_section(self, action_descriptions: dict[str, str]) -> str:
        if not action_descriptions:
            return ""
        lines = ["", "YOUR CUSTOM ACTIONS (use directly — do NOT re-innovate these):"]
        for name, desc in action_descriptions.items():
            lines.append(
                f'  - {name}: {desc} → use: {{"action": "{name}", "reason": "..."}}'
            )
        return "\n".join(lines)
