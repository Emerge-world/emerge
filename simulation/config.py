"""
Global simulation configuration.
"""

# --- World ---
WORLD_WIDTH = 15
WORLD_HEIGHT = 15
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
OLLAMA_MODEL = "qwen3.5:9b"
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 768

# --- Simulation ---
MAX_TICKS = 100  # maximum ticks per run
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

# --- Base actions ---
BASE_ACTIONS = ["move", "eat", "rest", "innovate"]
