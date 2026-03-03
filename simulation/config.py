"""
Global simulation configuration.
"""

# --- World ---
WORLD_WIDTH = 10
WORLD_HEIGHT = 10
TILE_WATER = "water"
TILE_LAND = "land"
TILE_TREE = "tree"

# World generation probabilities
WORLD_WATER_PROB = 0.15
WORLD_TREE_PROB = 0.10  # on land tiles

# --- Agents ---
MAX_AGENTS = 5
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
ENERGY_COST_INNOVATE = 0
ENERGY_RECOVERY_REST = 50
ENERGY_LOW_THRESHOLD = 20    # below this, agent feels tired/dizzy (prompt signal)
ENERGY_DAMAGE_PER_TICK = 2   # life lost per tick when energy == 0

# Perception
AGENT_VISION_RADIUS = 3  # tiles in each direction

# --- LLM / Ollama ---
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:3b"
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 512

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

# --- Day/Night cycle ---
DAY_LENGTH = 24               # ticks per in-world day (1 tick = 1 hour)
WORLD_START_HOUR = 6          # hour at which the simulation starts (0–23)
SUNSET_START_HOUR = 16        # hour when sunset begins
NIGHT_START_HOUR = 21         # hour when night begins
NIGHT_VISION_REDUCTION = 2    # vision radius reduced by this amount at night (3 → 1)
SUNSET_VISION_REDUCTION = 1   # vision radius reduced by this amount at sunset (3 → 2)
NIGHT_ENERGY_MULTIPLIER = 1.5 # energy action costs multiplied by this at night

# --- Base actions ---
BASE_ACTIONS = ["move", "eat", "rest", "innovate"]
