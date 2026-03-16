"""
Pydantic v2 schemas for all LLM-structured responses.
These are used with vllm's guided_json constrained decoding.
"""

from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, Field


IdentifierText = Annotated[str, Field(max_length=64)]
DirectionText = Annotated[str, Field(max_length=16)]
ReasonText = Annotated[str, Field(max_length=160)]
MediumText = Annotated[str, Field(max_length=240)]
LongText = Annotated[str, Field(max_length=280)]
SignalText = Annotated[str, Field(max_length=120)]


class PhysicalReflectionResponse(BaseModel):
    possible: bool
    reason: ReasonText
    life_damage: int = 0


class InnovationCategory(str, Enum):
    SURVIVAL = "SURVIVAL"
    CRAFTING = "CRAFTING"
    EXPLORATION = "EXPLORATION"
    SOCIAL = "SOCIAL"


class InnovationValidationResponse(BaseModel):
    approved: bool
    reason: ReasonText
    category: InnovationCategory
    aggressive: bool = False
    trust_impact: float = 0.0


class EffectsModel(BaseModel):
    hunger: int = 0
    energy: int = 0
    life: int = 0


class CustomActionOutcomeResponse(BaseModel):
    success: bool
    message: MediumText
    effects: EffectsModel


class ItemEatEffectResponse(BaseModel):
    possible: bool
    hunger_reduction: int
    life_change: int
    reason: ReasonText


class InnovationRequires(BaseModel):
    """Requirements declared by the agent for an innovation action."""
    tile: Optional[IdentifierText] = None
    min_energy: Optional[int] = None
    items: Optional[dict[str, int]] = None


class AgentDecisionResponse(BaseModel):
    action: IdentifierText
    reason: ReasonText
    direction: Optional[DirectionText] = None       # move
    new_action_name: Optional[IdentifierText] = None  # innovate
    description: Optional[LongText] = None     # innovate
    requires: Optional[InnovationRequires] = None    # innovate
    produces: Optional[dict[str, int]] = None        # innovate
    target: Optional[IdentifierText] = None          # communicate / give_item / teach / reproduce
    message: Optional[LongText] = None         # communicate
    intent: Optional[IdentifierText] = None          # communicate
    item: Optional[IdentifierText] = None            # give_item / eat (inventory) / drop_item
    quantity: Optional[int] = None        # give_item / drop_item
    skill: Optional[IdentifierText] = None           # teach


class PlanSubgoalResponse(BaseModel):
    description: MediumText
    kind: IdentifierText
    target: Optional[IdentifierText] = None
    preconditions: list[SignalText] = Field(default_factory=list)
    completion_signal: SignalText
    failure_signal: SignalText
    priority: int = 1


class AgentPlanResponse(BaseModel):
    goal: ReasonText
    goal_type: IdentifierText
    subgoals: list[PlanSubgoalResponse] = Field(default_factory=list)
    horizon: IdentifierText
    success_signals: list[SignalText] = Field(default_factory=list)
    abort_conditions: list[SignalText] = Field(default_factory=list)
    confidence: float
    rationale_summary: MediumText


class FruitEffectResponse(BaseModel):
    value: int


class MemoryCompressionResponse(BaseModel):
    learnings: list[MediumText]
