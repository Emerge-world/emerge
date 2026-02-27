"""
Global simulation configuration.
"""

# --- World ---
WORLD_WIDTH = 50
WORLD_HEIGHT = 50
TILE_WATER = "water"
TILE_LAND = "land"
TILE_TREE = "tree"

# World generation probabilities
WORLD_WATER_PROB = 0.15
WORLD_TREE_PROB = 0.20  # on land tiles

# --- Agents ---
MAX_AGENTS = 5
AGENT_MAX_LIFE = 100
AGENT_MAX_HUNGER = 100
AGENT_MAX_ENERGY = 100
AGENT_START_LIFE = 100
AGENT_START_HUNGER = 0      # 0 = not hungry, 100 = starving
AGENT_START_ENERGY = 100

# Thresholds and rates
HUNGER_PER_TICK = 3           # hunger increases each tick
HUNGER_DAMAGE_THRESHOLD = 70  # above this, hunger damages life
HUNGER_DAMAGE_PER_TICK = 5    # life damage when hunger > threshold
ENERGY_COST_MOVE = 5
ENERGY_COST_EAT = 2
ENERGY_COST_INNOVATE = 0
ENERGY_RECOVERY_REST = 15

# Perception
AGENT_VISION_RADIUS = 3  # tiles in each direction

# --- LLM / Ollama ---
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:3b"
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 512

# --- Simulation ---
MAX_TICKS = 100  # maximum ticks per run
TICK_DELAY_SECONDS = 0.5  # pause between ticks for console readability

# --- Logging ---
LOG_DIR = "logs"

# --- Base actions ---
BASE_ACTIONS = ["move", "eat", "rest", "innovate"]
