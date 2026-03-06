# Prompt Redesign for World Complexity — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update agent and oracle prompts to reflect 8 tile types, inject current tile context per tick, and calibrate oracle effect guidelines — while keeping tile properties emergent (discovered through experience, not told upfront).

**Architecture:** Two code changes (ASCII grid renderer, prompt variable injection) + five prompt file replacements. The `_build_ascii_grid()` method in `agent.py` renders all non-water tiles as `.` — a bug that makes the world unreadable. The `_build_decision_prompt()` method needs one new variable `current_tile_info` sourced from `nearby_tiles` (already available). Oracle prompts get tile catalog and calibrated effect tables.

**Tech Stack:** Python, prompt templates (`prompt_loader.render()`), pytest

---

## Task 1: Fix ASCII grid renderer — all 8 tile types

**Files:**
- Modify: `simulation/agent.py:165-188` (`_build_ascii_grid`)
- Test: `tests/test_agent_prompts.py` (new file)

**Step 1: Write the failing test**

```python
# tests/test_agent_prompts.py
import pytest
from simulation.agent import Agent

def _make_nearby(center_tile: str, *extra: dict) -> list[dict]:
    """Build a nearby_tiles list with the agent at (5,5) on center_tile."""
    tiles = [{"x": 5, "y": 5, "tile": center_tile, "distance": 0}]
    tiles.extend(extra)
    return tiles

class TestBuildAsciiGrid:
    def setup_method(self):
        Agent._id_counter = 0
        self.agent = Agent(name="Test", x=5, y=5)

    def test_sand_renders_S(self):
        nearby = _make_nearby("sand")
        grid = self.agent._build_ascii_grid(nearby)
        assert "@" in grid  # agent marker at center

    def test_all_tile_chars(self):
        """Each tile type renders to the correct character in the grid."""
        expected = {
            "land":     ".",
            "sand":     "S",
            "water":    "W",
            "river":    "~",
            "forest":   "f",
            "mountain": "M",
            "cave":     "C",
            "tree":     "t",  # empty tree (no resource)
        }
        for tile_type, char in expected.items():
            nearby = [
                {"x": 5, "y": 5, "tile": "land", "distance": 0},  # agent tile
                {"x": 6, "y": 5, "tile": tile_type, "distance": 1},  # east tile
            ]
            grid = self.agent._build_ascii_grid(nearby)
            row_center = grid.split("\n")[3]  # middle row of 7x7 grid
            assert char in row_center, f"Expected '{char}' for tile '{tile_type}'"

    def test_fruit_tree_renders_F(self):
        nearby = [
            {"x": 5, "y": 5, "tile": "land", "distance": 0},
            {"x": 6, "y": 5, "tile": "tree", "distance": 1,
             "resource": {"type": "fruit", "quantity": 3}},
        ]
        grid = self.agent._build_ascii_grid(nearby)
        row_center = grid.split("\n")[3]
        assert "F" in row_center
```

**Step 2: Run test to verify it fails**

```bash
cd /home/gusy/emerge && uv run pytest tests/test_agent_prompts.py -v
```
Expected: FAIL — `sand` renders as `.` not `S`

**Step 3: Fix `_build_ascii_grid()` in `simulation/agent.py:178-184`**

Replace the `elif (nx, ny) in tile_map:` block:

```python
elif (nx, ny) in tile_map:
    t = tile_map[(nx, ny)]
    tile_type = t["tile"]
    TILE_CHARS = {
        "tree":     lambda t: "F" if "resource" in t else "t",
        "water":    lambda _: "W",
        "sand":     lambda _: "S",
        "forest":   lambda _: "f",
        "mountain": lambda _: "M",
        "cave":     lambda _: "C",
        "river":    lambda _: "~",
        "land":     lambda _: ".",
    }
    char_fn = TILE_CHARS.get(tile_type, lambda _: ".")
    row_chars.append(char_fn(t))
```

**Step 4: Run tests**

```bash
cd /home/gusy/emerge && uv run pytest tests/test_agent_prompts.py -v
```
Expected: PASS

**Step 5: Run full test suite**

```bash
cd /home/gusy/emerge && uv run pytest -m "not slow" -q
```
Expected: all passing

**Step 6: Commit**

```bash
cd /home/gusy/emerge && git add simulation/agent.py tests/test_agent_prompts.py
git commit -m "$(cat <<'EOF'
fix(agent): render all 8 tile types correctly in ASCII grid

Previously all non-water, non-tree tiles rendered as '.'. Now sand=S,
forest=f, mountain=M, cave=C, river=~.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Inject `$current_tile_info` into decision prompt

**Files:**
- Modify: `simulation/agent.py:224-255` (`_build_decision_prompt`)
- Test: `tests/test_agent_prompts.py` (extend)

**Step 1: Write the failing test**

Add to `tests/test_agent_prompts.py`:

```python
class TestCurrentTileInfo:
    def setup_method(self):
        Agent._id_counter = 0
        self.agent = Agent(name="Test", x=5, y=5)

    def test_decision_prompt_contains_current_tile(self):
        """decision prompt shows [Tile: cave] when agent is on cave."""
        nearby = [
            {"x": 5, "y": 5, "tile": "cave", "distance": 0},
        ]
        prompt = self.agent._build_decision_prompt(nearby, tick=1)
        assert "[Tile: cave]" in prompt

    def test_decision_prompt_tile_changes_with_position(self):
        """different tile types appear correctly."""
        for tile_type in ["land", "sand", "forest", "mountain", "river"]:
            nearby = [{"x": 5, "y": 5, "tile": tile_type, "distance": 0}]
            prompt = self.agent._build_decision_prompt(nearby, tick=1)
            assert f"[Tile: {tile_type}]" in prompt
```

**Step 2: Run test to verify it fails**

```bash
cd /home/gusy/emerge && uv run pytest tests/test_agent_prompts.py::TestCurrentTileInfo -v
```
Expected: FAIL — `[Tile: cave]` not in prompt (variable `$current_tile_info` rendered as empty string or literally)

**Step 3: Update `_build_decision_prompt()` in `simulation/agent.py`**

At `agent.py:226`, add after `ascii_grid = self._build_ascii_grid(nearby_tiles)`:

```python
# Determine current tile type from nearby_tiles (distance=0 = agent's own tile)
_current = next(
    (t["tile"] for t in nearby_tiles if t["x"] == self.x and t["y"] == self.y),
    "land",
)
current_tile_info = f"[Tile: {_current}]"
```

Then add `current_tile_info=current_tile_info` to the `prompt_loader.render()` call (around `agent.py:239`).

**Step 4: Run tests**

```bash
cd /home/gusy/emerge && uv run pytest tests/test_agent_prompts.py -v
```
Expected: PASS

**Step 5: Run full suite**

```bash
cd /home/gusy/emerge && uv run pytest -m "not slow" -q
```
Expected: all passing

**Step 6: Commit**

```bash
cd /home/gusy/emerge && git add simulation/agent.py tests/test_agent_prompts.py
git commit -m "$(cat <<'EOF'
feat(agent): inject current tile type into decision prompt

Adds [Tile: X] line to per-tick decision prompt so agents know what
terrain they are standing on (needed for valid requires.tile in innovations).
Tile is sourced from nearby_tiles distance=0 entry.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Update `prompts/agent/system.txt`

**Files:**
- Modify: `prompts/agent/system.txt`

No test needed — this is a prompt text change. Verified by smoke test at the end.

**Step 1: Replace `prompts/agent/system.txt` entirely**

```
You are $name, a human trying to survive in a 2D world.
You must choose actions wisely to stay alive.

Available actions: $actions

GRID LEGEND:
  @=you  .=land  S=sand  ~=river  W=water
  F=fruit-tree  t=empty-tree  f=forest  M=mountain  C=cave  #=bounds

Action format — respond with a JSON object:
- move: {"action": "move", "direction": "north|northeast|east|southeast|south|southwest|west|northwest", "reason": "..."}
- eat: {"action": "eat", "reason": "..."} (eat food at current or adjacent tile)
- rest: {"action": "rest", "reason": "..."} (recover energy, skip turn)
- pickup: {"action": "pickup", "reason": "..."} (collect 1 item from current tile into inventory)
- innovate: {"action": "innovate", "new_action_name": "...", "description": "...", "reason": "...", "requires": {"tile": "cave|forest|mountain|river|...", "min_energy": <n>, "items": {"stone": 2}}, "produces": {"knife": 1}}
  (requires and produces are optional. Use requires.tile when the action only makes sense in a specific terrain type. Use produces when your action creates a physical item from materials.)
- For approved innovations: {"action": "<action_name>", "reason": "...", ...extra_params}

DIRECTIONS: north=up south=down west=left east=right (+ diagonals: northeast, northwest, southeast, southwest)

Always respond ONLY with a valid JSON object. Be strategic about survival.
```

**Step 2: Verify no template variables broken**

```bash
cd /home/gusy/emerge && uv run main.py --no-llm --ticks 3 --agents 1
```
Expected: runs without crash, no `$name` or `$actions` appearing literally in output

**Step 3: Commit**

```bash
cd /home/gusy/emerge && git add prompts/agent/system.txt
git commit -m "$(cat <<'EOF'
feat(prompts): update agent system prompt for 8 tile types

Expanded grid legend to include all 8 tile types (S=sand, ~=river,
f=forest, M=mountain, C=cave). Removed tile property hints — agents
discover cave rest bonus and mountain energy cost through experience.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Update `prompts/agent/decision.txt`

**Files:**
- Modify: `prompts/agent/decision.txt`

**Step 1: Replace `prompts/agent/decision.txt` entirely**

```
$time_info
$current_tile_info
TICK $tick - What do you do next?

YOUR STATS: Life=$life/$max_life, Hunger=$hunger/$max_hunger (danger at ${hunger_threshold}+), Energy=$energy/$max_energy
$status_effects
$inventory_info
YOUR VISION (7x7 grid, you are @):
$ascii_grid

NEARBY RESOURCES:
$resource_hints

YOUR MEMORY:
$memory_text

Respond with a JSON object.
```

**Step 2: Run smoke test**

```bash
cd /home/gusy/emerge && uv run main.py --no-llm --ticks 3 --agents 1 --verbose
```
Expected: `[Tile: X]` appears in agent decision output, no literal `$current_tile_info`

**Step 3: Commit**

```bash
cd /home/gusy/emerge && git add prompts/agent/decision.txt
git commit -m "$(cat <<'EOF'
feat(prompts): add current tile context to agent decision prompt

Adds $current_tile_info line showing [Tile: X] so agents know what
terrain they stand on when choosing actions.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Update oracle prompts

**Files:**
- Modify: `prompts/oracle/physical_system.txt`
- Modify: `prompts/oracle/innovation_system.txt`
- Modify: `prompts/oracle/custom_action_system.txt`

**Step 1: Replace `prompts/oracle/physical_system.txt`**

```
You are the Oracle of a primitive human survival simulation. You enforce the laws of physics — not agent safety.
"Possible" means: can a human physically attempt this action? Not: is it wise or safe?
All tile types are physically traversable (land, sand, tree, forest, mountain, cave, river, water). A human can wade into water or climb a mountain. They may suffer consequences, but the action itself is possible.
Only return false for actions that are literally impossible: flying unaided, teleporting, phasing through solid rock, etc.
Be consistent: your rulings become permanent precedents.
Respond with JSON: {"possible": true/false, "reason": "brief explanation"}
```

**Step 2: Replace `prompts/oracle/innovation_system.txt`**

```
You are the Oracle of a survival simulation world. You judge whether new actions invented by agents are reasonable and meaningfully different from existing actions.

Valid tile types for requires.tile: land, sand, tree, forest, mountain, cave, river, water.

Be fair but realistic:
- Simple survival innovations (foraging, fishing, drinking, mining, building, crafting) are usually approved.
- Impossible or magical actions should be rejected.
- Innovations that merely duplicate an existing action under a different name should be rejected.

Category must be one of: SURVIVAL (food, water, basic shelter), CRAFTING (tools, items), EXPLORATION (scouting, mapping), SOCIAL (communication, cooperation).
For CRAFTING: verify that the proposed produces output is physically plausible given requires.items (stone → knife: OK; fruit → metal: reject). If produces is absent, infer category from description.

Respond with JSON: {"approved": true/false, "reason": "...", "category": "..."}
```

**Step 3: Replace `prompts/oracle/custom_action_system.txt`**

```
You are the Oracle of a survival simulation. You determine outcomes of custom actions fairly and consistently.

Effect guidelines:
- Light physical labor (foraging, drinking, scouting): -3 to -8 energy
- Moderate labor (fishing, shelter-building, small crafting): -8 to -15 energy
- Heavy labor (mining, heavy crafting, hauling): -15 to -20 energy
- Food/drink actions reduce hunger by 10-30 (scale by item quality/quantity)
- Dangerous or risky actions may cost 1-10 life
- Do NOT include terrain movement costs (handled by game engine separately)
- For crafting actions: determine only the energy cost of physical labor. Item consumption and production are handled by deterministic code — do not include them in effects.

Be deterministic: similar actions in similar contexts produce similar results.
Respond with JSON: {"effects": {"energy": -10, "hunger": -5, "life": 0}, "description": "brief outcome"}
```

**Step 4: Run full test suite**

```bash
cd /home/gusy/emerge && uv run pytest -m "not slow" -q
```
Expected: all passing (oracle prompts only run with live LLM; tests use mocks)

**Step 5: Commit**

```bash
cd /home/gusy/emerge && git add prompts/oracle/physical_system.txt prompts/oracle/innovation_system.txt prompts/oracle/custom_action_system.txt
git commit -m "$(cat <<'EOF'
feat(prompts): update oracle prompts for world complexity

- physical_system: all tile types are traversable (even water)
- innovation_system: lists valid tile names for requires.tile, expands approved examples
- custom_action_system: 3-tier energy cost calibration table

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: End-to-end verification

**Step 1: Full smoke test**

```bash
cd /home/gusy/emerge && uv run main.py --no-llm --ticks 24 --agents 3 --seed 42
```
Expected: runs 24 ticks, no crashes, no literal `$current_tile_info` in output

**Step 2: Audit mode — confirm grid readability**

```bash
cd /home/gusy/emerge && uv run main.py --no-llm --ticks 5 --agents 1 --audit
```
Expected: ASCII grid shows S, f, M, C, ~ chars (not all `.`) depending on world seed

**Step 3: Full test suite**

```bash
cd /home/gusy/emerge && uv run pytest -m "not slow" -v
```
Expected: all passing

**Step 4 (optional, requires Ollama): LLM test**

```bash
cd /home/gusy/emerge && uv run main.py --agents 2 --ticks 30 --seed 42 --verbose
```
Watch for: agents writing `requires.tile: "mountain"` or `requires.tile: "river"` in innovations. `[Tile: X]` appears in decision context.
