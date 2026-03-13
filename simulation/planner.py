from simulation import prompt_loader
from simulation.planning_state import PlanningState, PlanningSubgoal
from simulation.schemas import AgentPlanResponse


class Planner:
    def __init__(self, llm):
        self.llm = llm
        self.last_call: dict = {}

    def plan(
        self,
        agent_name: str,
        tick: int,
        observation_text: str,
        planner_context: list[str],
        current_plan: PlanningState | None = None,
    ) -> PlanningState | None:
        if not self.llm:
            self.last_call = {}
            return None

        system_prompt = prompt_loader.render("agent/planner_system", agent_name=agent_name)
        user_prompt = prompt_loader.render(
            "agent/planner",
            tick=tick,
            observation_text=observation_text,
            planner_context="\n".join(f"- {entry}" for entry in planner_context) or "- none",
            current_plan=(current_plan.goal if current_plan else "none"),
        )
        typed = self.llm.generate_structured(
            user_prompt,
            AgentPlanResponse,
            system_prompt=system_prompt,
            temperature=0.3,
        )
        if typed is None:
            self.last_call = {}
            return None

        llm_trace = dict(self.llm.last_call) if self.llm.last_call else {}
        self.last_call = {
            "system_prompt": llm_trace.get("system_prompt", system_prompt),
            "user_prompt": llm_trace.get("user_prompt", user_prompt),
            "raw_response": llm_trace.get("raw_response", ""),
            "parsed_plan": typed.model_dump(),
        }

        return PlanningState(
            goal=typed.goal,
            goal_type=typed.goal_type,
            subgoals=[
                PlanningSubgoal(
                    description=subgoal.description,
                    kind=subgoal.kind,
                    target=subgoal.target,
                    preconditions=list(subgoal.preconditions),
                    completion_signal=subgoal.completion_signal,
                    failure_signal=subgoal.failure_signal,
                    priority=subgoal.priority,
                )
                for subgoal in typed.subgoals
            ],
            active_subgoal_index=0,
            status="active",
            created_tick=tick,
            last_plan_tick=tick,
            last_progress_tick=tick,
            confidence=typed.confidence,
            horizon=typed.horizon,
            success_signals=list(typed.success_signals),
            abort_conditions=list(typed.abort_conditions),
            blockers=[],
            rationale_summary=typed.rationale_summary,
        )
