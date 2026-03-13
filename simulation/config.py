"""
Global simulation configuration.
"""

# --- World ---
WORLD_WIDTH = 15
WORLD_HEIGHT = 15
TILE_WATER = "water"
TILE_LAND = "land"
TILE_TREE = "tree"
# New tile types (Phase 2)
TILE_SAND     = "sand"
TILE_FOREST   = "forest"
TILE_MOUNTAIN = "mountain"
TILE_CAVE     = "cave"
TILE_RIVER    = "river"

# Risk applied when an agent enters this tile type.
# life_damage: flat life points lost on entry (0 = none).
#   River life_damage is set to 0 here; Oracle LLM may add more based on current strength.
# energy_cost_add: additional energy cost beyond ENERGY_COST_MOVE.
TILE_RISKS = {
    TILE_RIVER:    {"life_damage": 0,  "energy_cost_add": 3},
    TILE_MOUNTAIN: {"life_damage": 0,  "energy_cost_add": 6},
}

# Extra energy recovery when resting on this tile (stacks with ENERGY_RECOVERY_REST).
TILE_REST_BONUS = {
    TILE_CAVE: {"energy_add": 20},
}

# Resources that spawn at world generation on each tile type.
TILE_RESOURCE_SPAWN = {
    TILE_TREE:     {"type": "fruit",    "min": 1, "max": 5},
    TILE_FOREST:   {"type": "mushroom", "min": 1, "max": 3},
    TILE_MOUNTAIN: {"type": "stone",    "min": 2, "max": 5},
    TILE_CAVE:     {"type": "stone",    "min": 1, "max": 4},
    TILE_RIVER:    {"type": "water",    "min": 99, "max": 99},
}

# World generation noise parameters.
WORLD_NOISE_SCALE       = 3.5   # controls biome feature size (lower = larger biomes)
WORLD_RIVER_NOISE_SCALE = 7.0   # secondary noise scale for river channel carving
WORLD_RIVER_THRESHOLD   = 0.15  # secondary noise value below which tile becomes river

# Height thresholds for tile assignment from Perlin heightmap (normalized 0–1).
WORLD_HEIGHT_WATER    = 0.28
WORLD_HEIGHT_SAND     = 0.38
WORLD_HEIGHT_LAND     = 0.70
WORLD_HEIGHT_TREE     = 0.76  # scattered trees (between land and dense forest)
WORLD_HEIGHT_FOREST   = 0.82
WORLD_HEIGHT_MOUNTAIN = 0.90
WORLD_HEIGHT_CAVE     = 0.96
# Height > WORLD_HEIGHT_CAVE → mountain peak (also TILE_MOUNTAIN type)

# World generation probabilities (legacy white-noise, kept for fallback reference)
WORLD_WATER_PROB = 0.15
WORLD_TREE_PROB = 0.10  # on land tiles

# --- Agents ---
MAX_AGENTS = 10
AGENT_MAX_LIFE = 100
AGENT_MAX_HUNGER = 100
AGENT_MAX_ENERGY = 100
AGENT_START_LIFE = 100
AGENT_START_HUNGER = 0      # 0 = not hungry, 100 = starving
AGENT_START_ENERGY = 100

# Thresholds and rates
HUNGER_PER_TICK = 1           # hunger increases each tick
HUNGER_DAMAGE_THRESHOLD = 80  # above this, hunger damages life
HUNGER_DAMAGE_PER_TICK = 3    # life damage when hunger > threshold
ENERGY_COST_MOVE = 3
ENERGY_COST_EAT = 2
ENERGY_COST_INNOVATE = 10
ENERGY_COST_PICKUP = 0
COMMUNICATE_ENERGY_COST = 3
COMMUNICATE_TRUST_DELTA = 0.05
GIVE_ITEM_ENERGY_COST = 2
GIVE_ITEM_TRUST_DELTA = 0.15
TEACH_ENERGY_COST_TEACHER = 8
TEACH_ENERGY_COST_LEARNER = 5
TEACH_TRUST_DELTA = 0.20
BONDING_TRUST_THRESHOLD = 0.75
BONDING_COOPERATION_MINIMUM = 3
ENERGY_RECOVERY_REST = 50
ENERGY_LOW_THRESHOLD = 20    # below this, agent feels tired/dizzy (prompt signal)
ENERGY_DAMAGE_PER_TICK = 2   # life lost per tick when energy == 0

# Passive healing
HEAL_HUNGER_THRESHOLD = 50   # must have hunger < this to heal
HEAL_ENERGY_THRESHOLD = 30   # must have energy > this to heal
HEAL_PER_TICK = 1            # life recovered per tick when conditions met

# Perception
AGENT_VISION_RADIUS = 3  # tiles in each direction

# --- LLM / vllm ---
VLLM_BASE_URL   = "http://localhost:8000/v1"
VLLM_MODEL      = "cyankiwi/Qwen3.5-35B-A3B-AWQ-4bit"
VLLM_API_KEY    = "EMPTY"
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS  = 768
DECISION_RESPONSE_MAX_TOKENS = 256
PLANNER_RESPONSE_MAX_TOKENS = 640
ORACLE_RESPONSE_MAX_TOKENS = 256
ORACLE_EFFECT_RESPONSE_MAX_TOKENS = 128

# --- Simulation ---
MAX_TICKS = 72   # maximum ticks per run (3 full in-world days)
TICK_DELAY_SECONDS = 0.5  # pause between ticks for console readability

# --- Logging ---
LOG_DIR = "logs"

# --- Audit thresholds (for context flags in behavioral analysis) ---
AUDIT_HUNGER_THRESHOLD = 60     # hunger above this = "was_hungry"
AUDIT_EXHAUSTION_THRESHOLD = 20 # energy below this = "was_exhausted"
AUDIT_HUNGER_CRITICAL = 80      # hunger above this = "hunger_critical"

# --- Memory ---
MEMORY_EPISODIC_MAX = 20
MEMORY_SEMANTIC_MAX = 30
MEMORY_COMPRESSION_INTERVAL = 10
MEMORY_EPISODIC_IN_PROMPT = 10
MEMORY_SEMANTIC_IN_PROMPT = 10
TASK_MEMORY_MAX = 12
PLANNER_CONTEXT_MAX = 6
EXECUTOR_CONTEXT_MAX = 4

# --- Planning ---
ENABLE_EXPLICIT_PLANNING = False
PLAN_REFRESH_INTERVAL = 5

# --- Day/Night cycle ---
DAY_LENGTH = 24               # ticks per in-world day (1 tick = 1 hour)
WORLD_START_HOUR = 6          # hour at which the simulation starts (0–23)
SUNSET_START_HOUR = 16        # hour when sunset begins
NIGHT_START_HOUR = 21         # hour when night begins
NIGHT_VISION_REDUCTION = 2    # vision radius reduced by this amount at night (3 → 1)
SUNSET_VISION_REDUCTION = 1   # vision radius reduced by this amount at sunset (3 → 2)
NIGHT_ENERGY_MULTIPLIER = 1.5 # energy action costs multiplied by this at night

# --- Innovation ---
# Safe bounds for stat deltas returned by the oracle when judging custom actions.
# Any value outside these ranges is clamped. (min, max)
INNOVATION_EFFECT_BOUNDS = {
    "hunger": (-30, 10),
    "energy": (-20, 20),
    "life":   (-15, 10),
}

# --- Reproduction ---
REPRODUCE_MIN_LIFE = 70           # both parents must have at least this life
REPRODUCE_MAX_HUNGER = 30         # both parents must have hunger below this
REPRODUCE_MIN_ENERGY = 50         # both parents must have at least this energy
REPRODUCE_MIN_TICKS_ALIVE = 100   # both parents must have survived at least this many ticks
REPRODUCE_ADJACENCY_MAX = 1       # Manhattan distance: must be adjacent
REPRODUCE_COOLDOWN = 48           # ticks between reproduce attempts per agent

# Cost to BOTH parents on successful reproduction
REPRODUCE_LIFE_COST = 30
REPRODUCE_HUNGER_COST = 30        # hunger increases (more hungry after)
REPRODUCE_ENERGY_COST = 30

# Child initial stats (vulnerable infant)
CHILD_START_LIFE = 50
CHILD_START_HUNGER = 40
CHILD_START_ENERGY = 40

# Trait mutation standard deviation for personality blending
PERSONALITY_MUTATION_STD = 0.1

# Max semantic memories inherited from each parent
INHERIT_SEMANTIC_MAX = 5

# Extended name pool (30+ names for new generations)
AGENT_NAME_POOL = [
    "Ada", "Bruno", "Clara", "Dante", "Elena",
    "Felix", "Gaia", "Hugo", "Iris", "Joel",
    "Kira", "Leo", "Maya", "Niko", "Ora",
    "Pax", "Quinn", "Rosa", "Soren", "Tara",
    "Uma", "Veer", "Wren", "Xen", "Yara",
    "Zoe", "Ash", "Beau", "Cade", "Dara",
    "Eli", "Fern",
]

# --- Built-in actions ---
# Initial actions are available from tick 0.
INITIAL_ACTIONS = [
    "move",
    "eat",
    "rest",
    "innovate",
    "pickup",
    "communicate",
    "give_item",
    "teach",
]

# Unlockable actions are built-in, but not available from birth.
AGE_UNLOCKED_ACTIONS = {
    "reproduce": REPRODUCE_MIN_TICKS_ALIVE,
}

# BASE_ACTIONS remains the canonical built-in/non-innovation action list.
BASE_ACTIONS = INITIAL_ACTIONS + list(AGE_UNLOCKED_ACTIONS)

# --- Inventory ---
AGENT_INVENTORY_CAPACITY = 10   # maximum total items an agent can carry

# --- Resource regeneration ---
RESOURCE_REGEN_CHANCE = 0.3          # probability per depleted tree at each dawn
RESOURCE_REGEN_AMOUNT_MIN = 1        # minimum fruit spawned on regeneration
RESOURCE_REGEN_AMOUNT_MAX = 3        # maximum fruit spawned on regeneration
