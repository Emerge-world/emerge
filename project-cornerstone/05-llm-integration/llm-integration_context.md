# 05 — LLM Integration

## Current State (Phase 0)

- **Model**: Qwen 2.5-3B via Ollama
- **Calls per tick**: N agents (decision) + 0-N oracle (only if innovation/custom)
- **Format**: Mandatory JSON in all responses
- **Fallback**: If Ollama is down or JSON is invalid → automatic fallback to simple rules

## Bottleneck Analysis

With 5 agents and Qwen 2.5-3B:
- Agent decision: ~1-3s per call
- Oracle validation: ~1-3s (only if innovation)
- **Worst case per tick**: 5 agents × 3s + 2 oracle × 3s = 21s/tick
- **100 ticks** = ~35 minutes

### Priority optimizations

1. **Parallelize agent decisions** (Phase 1)
   ```python
   # Agents don't interact (Phase 0-2), so their decisions are independent
   import concurrent.futures
   
   with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
       futures = {
           executor.submit(agent.decide_action, nearby, tick): agent
           for agent in alive_agents
       }
       decisions = {}
       for future in concurrent.futures.as_completed(futures):
           agent = futures[future]
           decisions[agent.id] = future.result()
   ```

2. **Compact prompt** (Phase 1)
   - Visual grid instead of JSON list of tiles
   - Compressed memory (semantic) instead of raw events
   - Target: <300 tokens input per call (current actual: ~500-750 tokens with dual memory; compact grid + memory compression implemented, token budget enforcement pending)

3. **Ollama keep_alive** (Phase 1)
   ```python
   # Keep model in memory between calls
   # In payload: "keep_alive": "10m"
   # This avoids reloading the model between agents in the same tick
   ```

4. **Batch with Ollama** (Phase 2)
   - Ollama doesn't have native batch, but we can use its concurrency
   - Configure `OLLAMA_NUM_PARALLEL=5` on the server

## Prompt Engineering Rules

### For the agent (decision)

```
RULES:
- System prompt: FIXED between ticks (leverage caching). Includes: name, personality, 
  game rules, JSON format, few-shot examples.
- User prompt: VARIABLE each tick. Includes: tick number, stats, visual grid, memory.
- Temperature: 0.7 (creative but not crazy)
- Max tokens: 512 (matches LLM_MAX_TOKENS in config.py)
```

### For the oracle (validation)

```
RULES:
- System prompt: oracle role, consistency rules, relevant precedents.
- User prompt: proposed action + agent context + world state.
- Temperature: 0.2-0.3 (as deterministic as possible)
- Max tokens: 256
- INCLUDE similar precedents in prompt to guide consistency.
```

### JSON Parsing Robustness

The 3B model sometimes fails at JSON. Defense layers:

```
1. Try json.loads() directly
2. Clean code fences (```json ... ```)
3. Find first { and last }
4. Regex to extract key fields
5. Fallback to default action
→ NEVER crash due to invalid JSON
```

## Model Upgrade Path

| Phase | Model               | Reason                                     |
|-------|---------------------|--------------------------------------------|
| 0-1   | Qwen 2.5-3B        | Fast, local, sufficient for decisions      |
| 2     | Qwen 2.5-7B        | Better for complex innovations             |
| 3     | Llama 3 8B         | Better at dialogue for social interaction  |
| 4     | Claude Haiku (API) | Necessary for evolution/culture            |
| 5     | Claude Sonnet (API)| For analysis and narration                 |

### Provider abstraction

```python
# Base interface for any LLM
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: str, temperature: float) -> str: ...
    
    @abstractmethod
    def generate_json(self, prompt: str, system: str, temperature: float) -> dict | None: ...

class OllamaProvider(LLMProvider): ...
class AnthropicProvider(LLMProvider): ...
class OpenAIProvider(LLMProvider): ...

# Selection by config:
# AGENT_LLM_PROVIDER = "ollama"
# ORACLE_LLM_PROVIDER = "anthropic"  # Oracle can use more powerful model
```

## Considerations for Claude Code

- Each prompt change MUST include a before/after with output example.
- Don't optimize prematurely: if it works with 3s/call, it's sufficient for Phase 1.
- Agent and oracle prompts are the MOST SENSITIVE files in the project. Small changes have big effects.
- Always test prompts with `--ticks 5 --agents 1 --verbose` before running long simulations.
- If changing models, re-evaluate ALL prompts. Don't assume what works in Qwen works in Llama.
