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

    def build_executor_decision(
        self,
        *,
        tick: int,
        time_info: str,
        current_tile_info: str,
        life: int,
        max_life: int,
        hunger: int,
        max_hunger: int,
        hunger_threshold: int,
        energy: int,
        max_energy: int,
        status_effects: str,
        inventory_info: str,
        ascii_grid: str,
        pickup_ready_resources: str,
        nearby_resource_hints: str,
        social_context: dict[str, str],
        planning_context: dict[str, str],
        family_info: str,
        memory_text: str,
        reproduction_hint: str,
    ) -> str:
        return self._normalize(
            prompt_loader.render(
                "agent/decision",
                tick=tick,
                time_info=time_info,
                current_tile_info=current_tile_info,
                life=life,
                max_life=max_life,
                hunger=hunger,
                max_hunger=max_hunger,
                hunger_threshold=hunger_threshold,
                energy=energy,
                max_energy=max_energy,
                status_effects=status_effects,
                inventory_info=inventory_info,
                ascii_grid=ascii_grid,
                pickup_ready_resources=pickup_ready_resources,
                nearby_resource_hints=nearby_resource_hints,
                social_context_block=self._social_context_block(social_context),
                planning_status_block=self._planning_status_block(planning_context),
                family_block=self._family_block(family_info),
                memory_text=memory_text,
                reproduction_hint_block=self._reproduction_hint_block(
                    reproduction_hint
                ),
                decision_reflection_questions=self._decision_reflection_questions(),
            )
        )

    def build_planner_system(self, *, agent_name: str) -> str:
        return self._normalize(
            prompt_loader.render(
                "agent/planner_system",
                agent_name=agent_name,
                planner_capability_guidance=self._planner_capability_guidance(),
            )
        )

    def build_planner_prompt(
        self,
        *,
        tick: int,
        observation_text: str,
        planner_context: list[str],
        current_plan: str,
    ) -> str:
        return self._normalize(
            prompt_loader.render(
                "agent/planner",
                tick=tick,
                observation_text=observation_text,
                current_plan_block=self._current_plan_block(current_plan),
                planner_context="\n".join(f"- {entry}" for entry in planner_context)
                or "- none",
                planner_reflection_questions=self._planner_reflection_questions(),
            )
        )

    def build_planner_observation_text(
        self,
        *,
        life: int,
        hunger: int,
        energy: int,
        inventory_info: str,
        current_tile_resources: str,
        nearby_resources: str,
        nearby_agent_names: list[str],
        custom_actions: list[str],
        time_description: str,
    ) -> str:
        parts = []
        if time_description:
            parts.append(time_description.strip())
        parts.extend(
            [
                f"Stats: life={life}, hunger={hunger}, energy={energy}",
                f"Resources on current tile: {current_tile_resources or 'none'}",
                f"Nearby resources: {nearby_resources or 'none'}",
                f"Inventory: {self._planner_inventory_summary(inventory_info)}",
            ]
        )
        if self.agent_settings.social:
            nearby = ", ".join(nearby_agent_names) if nearby_agent_names else "none"
            parts.append(f"Nearby agents: {nearby}")
        if custom_actions:
            parts.append(f"Custom actions: {', '.join(custom_actions)}")
        return "\n".join(parts)

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

    def _social_context_block(self, social_context: dict[str, str]) -> str:
        if not self.agent_settings.social:
            return ""
        sections = [
            social_context.get("nearby_agents", ""),
            social_context.get("incoming_messages", ""),
            social_context.get("relationships", ""),
        ]
        return "\n".join(section for section in sections if section)

    def _planning_status_block(self, planning_context: dict[str, str]) -> str:
        if not self.agent_settings.explicit_planning:
            return ""
        return "\n".join(
            [
                "CURRENT GOAL:",
                planning_context.get("current_goal", "None."),
                "",
                "ACTIVE SUBGOAL:",
                planning_context.get("active_subgoal", "None."),
                "",
                "PLAN STATUS:",
                planning_context.get("plan_status", "No active plan."),
            ]
        )

    def _family_block(self, family_info: str) -> str:
        if not self.agent_settings.reproduction:
            return ""
        return f"FAMILY:\n{family_info}"

    def _reproduction_hint_block(self, reproduction_hint: str) -> str:
        if not self.agent_settings.reproduction:
            return ""
        return reproduction_hint

    def _current_plan_block(self, current_plan: str) -> str:
        if not self.agent_settings.explicit_planning:
            return ""
        return f"CURRENT PLAN:\n{current_plan}"

    def _decision_reflection_questions(self) -> str:
        lines = [
            "- What is the most urgent threat or opportunity right now?",
            "- Am I making progress, or repeating actions without improving my situation?",
        ]
        if self.agent_settings.innovation:
            lines.append(
                "- Is there a useful visible opportunity that current actions do not exploit yet?"
            )
        lines.append(self._long_horizon_reflection_question())
        lines.append(
            "- Would preserving energy or knowledge now create more options soon?"
        )
        if self.agent_settings.item_reflection:
            lines.append(
                "- If I am carrying an item whose full potential is unclear, reflecting on it (reflect_item_uses) may unlock new ways to use it."
            )
        return "\n".join(lines)

    def _long_horizon_reflection_question(self) -> str:
        options: list[str] = []
        if self.agent_settings.social:
            options.append("cooperation")
            if self.agent_settings.teach:
                options.append("teaching")
        options.append("repositioning")
        if self.agent_settings.reproduction:
            options.append("reproduction")
        return (
            "- If I am stable, would "
            f"{self._human_join(options)} create better long-term prospects?"
        )

    def _human_join(self, items: list[str]) -> str:
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} or {items[1]}"
        return f"{', '.join(items[:-1])}, or {items[-1]}"

    def _planner_capability_guidance(self) -> str:
        lines = [
            (
                "- When survival is stable (roughly hunger not high and energy not low), "
                f"longer-horizon subgoals often involve {self._planner_long_horizon_guidance()}."
            ),
            (
                "- Vary long-horizon goals across situations: "
                f"{self._planner_goal_variety_guidance()}."
            ),
        ]
        instability_guidance = self._planner_instability_guidance()
        if instability_guidance:
            lines.append(instability_guidance)
        return "\n".join(lines)

    def _planner_long_horizon_guidance(self) -> str:
        options = ["capability building"]
        if self.agent_settings.innovation:
            options.append("innovation")
        if self.agent_settings.social:
            options.append("cooperation")
            if self.agent_settings.teach:
                options.append("teaching")
        if self.agent_settings.reproduction:
            options.append("preparing favorable conditions for future reproduction")
        return self._human_join(options)

    def _planner_goal_variety_guidance(self) -> str:
        options = [
            "sometimes improve food/water access",
            "sometimes exploration",
            "sometimes tools",
        ]
        if self.agent_settings.social and self.agent_settings.reproduction:
            options.append("sometimes social/lineage opportunities")
        elif self.agent_settings.social:
            options.append("sometimes social opportunities")
        elif self.agent_settings.reproduction:
            options.append("sometimes lineage opportunities")
        return ", ".join(options)

    def _planner_instability_guidance(self) -> str:
        unstable_options = []
        if self.agent_settings.reproduction:
            unstable_options.append("reproduction")
        if self.agent_settings.innovation:
            unstable_options.append("innovation")
        if not unstable_options:
            return ""
        joined = self._human_join(unstable_options)
        if len(unstable_options) == 1:
            return (
                f"- Do not force {joined} when the situation is unstable; treat it as a "
                "strategic option, not an obligation."
            )
        return (
            f"- Do not force {joined} when the situation is unstable; treat them as "
            "strategic options, not obligations."
        )

    def _planner_reflection_questions(self) -> str:
        lines = ["- What most needs attention over the next few ticks?"]
        if self.agent_settings.social:
            lines.append(
                "- Am I getting closer to a better position, capability, or relationship?"
            )
        else:
            lines.append(
                "- Am I getting closer to a better position or capability?"
            )
        lines.append("- Am I repeating actions without progress?")
        if self.agent_settings.innovation:
            lines.append(
                "- Is there a blocked opportunity that suggests innovation or a different approach?"
            )
        strategic_options = []
        if self.agent_settings.social:
            strategic_options.append("cooperation")
            if self.agent_settings.teach:
                strategic_options.append("teaching")
        if self.agent_settings.reproduction:
            strategic_options.append("reproduction")
        if strategic_options:
            lines.append(
                "- If survival is stable, should I prepare for "
                f"{self._human_join(strategic_options)}?"
            )
        lines.append("- Do I need to change my goal?")
        return "\n".join(lines)

    def _planner_inventory_summary(self, inventory_info: str) -> str:
        if not inventory_info:
            return "empty"
        prefix = "INVENTORY: "
        if inventory_info.startswith(prefix):
            return inventory_info[len(prefix):]
        return inventory_info
