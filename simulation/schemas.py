"""
Pydantic v2 schemas for all LLM-structured responses.
These are used with vllm's guided_json constrained decoding.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PhysicalReflectionResponse(BaseModel):
    possible: bool
    reason: str
    life_damage: int = 0


class InnovationCategory(str, Enum):
    SURVIVAL = "SURVIVAL"
    CRAFTING = "CRAFTING"
    EXPLORATION = "EXPLORATION"
    SOCIAL = "SOCIAL"


class InnovationValidationResponse(BaseModel):
    approved: bool
    reason: str
    category: InnovationCategory
    aggressive: bool = False
    trust_impact: float = 0.0


class EffectsModel(BaseModel):
    hunger: int = 0
    energy: int = 0
    life: int = 0


class CustomActionOutcomeResponse(BaseModel):
    success: bool
    message: str
    effects: EffectsModel


class ItemEatEffectResponse(BaseModel):
    possible: bool
    hunger_reduction: int
    life_change: int
    reason: str


class AgentDecisionResponse(BaseModel):
    action: str
    reason: str
    direction: Optional[str] = None       # move
    new_action_name: Optional[str] = None  # innovate
    description: Optional[str] = None     # innovate
    target: Optional[str] = None          # communicate / give_item / teach / reproduce
    message: Optional[str] = None         # communicate
    intent: Optional[str] = None          # communicate
    item: Optional[str] = None            # give_item
    quantity: Optional[int] = None        # give_item
    skill: Optional[str] = None           # teach


class PlanSubgoalResponse(BaseModel):
    description: str
    kind: str
    target: Optional[str] = None
    preconditions: list[str] = Field(default_factory=list)
    completion_signal: str
    failure_signal: str
    priority: int = 1


class AgentPlanResponse(BaseModel):
    goal: str
    goal_type: str
    subgoals: list[PlanSubgoalResponse] = Field(default_factory=list)
    horizon: str
    success_signals: list[str] = Field(default_factory=list)
    abort_conditions: list[str] = Field(default_factory=list)
    confidence: float
    rationale_summary: str


class FruitEffectResponse(BaseModel):
    value: int


class MemoryCompressionResponse(BaseModel):
    learnings: list[str]
