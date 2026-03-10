# Design: vllm + outlines Structured Outputs

**Date:** 2026-03-10
**Status:** Approved

## Problem

The Emerge simulation calls Ollama via HTTP and parses LLM responses with soft prompts + regex cleanup. This silently falls back to defaults when the model returns malformed JSON, and there is no schema enforcement or type safety. Parse failures are invisible in normal operation.

## Solution

Replace the Ollama backend with vllm, which integrates outlines for constrained token generation. The model is constrained at inference time to emit valid JSON matching defined schemas — eliminating the entire parsing/repair layer.

## Architecture

```
Before:
  agent.py / oracle.py
    → LLMClient.generate_json()
    → Ollama HTTP (soft prompt: "respond only with JSON")
    → regex cleanup + JSON extraction + repair
    → dict (or None on failure)

After:
  agent.py / oracle.py
    → LLMClient.generate_structured(MySchema)
    → vllm HTTP (extra_body: {"guided_json": schema})
    → outlines constrained decoding at token level
    → MySchema instance (or None on connection/validation error)
```

The `--no-llm` fallback path (rule-based decisions) bypasses `llm_client` entirely — tests are unaffected.

## Response Schemas (Pydantic v2)

### PhysicalReflectionResponse
```python
class PhysicalReflectionResponse(BaseModel):
    possible: bool
    reason: str
    life_damage: int = 0
```

### InnovationValidationResponse
```python
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
```

### CustomActionOutcomeResponse
```python
class EffectsModel(BaseModel):
    hunger: int = 0
    energy: int = 0
    life: int = 0

class CustomActionOutcomeResponse(BaseModel):
    success: bool
    message: str
    effects: EffectsModel
```

### ItemEatEffectResponse
```python
class ItemEatEffectResponse(BaseModel):
    possible: bool
    hunger_reduction: int
    life_change: int
    reason: str
```

### AgentDecisionResponse
Flat schema with optional action-specific fields:
```python
class AgentDecisionResponse(BaseModel):
    action: str
    reason: str
    direction: Optional[str] = None        # move
    new_action_name: Optional[str] = None  # innovate
    description: Optional[str] = None      # innovate
    target: Optional[str] = None           # communicate / give_item / teach / reproduce
    message: Optional[str] = None          # communicate
    intent: Optional[str] = None           # communicate
    item: Optional[str] = None             # give_item
    quantity: Optional[int] = None         # give_item
    skill: Optional[str] = None            # teach
```

## Config Changes

Remove `OLLAMA_BASE_URL`, `OLLAMA_MODEL`. Add:
```python
VLLM_BASE_URL = "http://localhost:8000/v1"
VLLM_MODEL    = "Qwen/Qwen2.5-3B-Instruct"
VLLM_API_KEY  = "EMPTY"
```

## LLMClient API

```python
def generate_structured(
    self,
    prompt: str,
    response_model: type[T],
    system_prompt: str = "",
    temperature: float = LLM_TEMPERATURE,
) -> T | None:
    """Calls vllm with guided_json constraint. Returns typed model or None on error."""
```

Uses `openai.OpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)` internally.
`extra_body={"guided_json": response_model.model_json_schema()}` constrains token generation.

## Dependencies

- `openai>=1.0.0` added to `pyproject.toml` (vllm OpenAI-compatible client)
- `pydantic` already available via `fastapi`

## Verification

```bash
# 1. Confirm vllm is running
curl http://localhost:8000/v1/models

# 2. Unit tests (--no-llm path, no vllm needed)
uv run pytest -m "not slow"

# 3. Smoke test (no vllm needed)
uv run main.py --no-llm --ticks 5 --agents 1

# 4. Full run with vllm
uv run main.py --agents 3 --ticks 10 --seed 42
# Expected: zero "WARNING: Could not parse JSON" log lines
```
