/** One distinct color per agent index (up to 10; cycles after that). */
export const AGENT_COLORS = [
  '#f87171', // red
  '#fb923c', // orange
  '#fbbf24', // amber
  '#34d399', // green
  '#60a5fa', // blue
  '#c084fc', // purple
  '#f472b6', // pink
  '#a3e635', // lime
  '#2dd4bf', // teal
  '#e879f9', // fuchsia
] as const

/** Stat bar semantic colors — kept in sync with CSS tokens. */
export const STAT_COLORS = {
  life:   '#22c55e', // --green
  hunger: '#f97316', // --orange
  energy: '#3b82f6', // --blue
  danger: '#ef4444', // --danger
} as const

/** Canvas tile fallback colors (used when tileset.png is not present). */
export const TILE_COLORS: Record<string, string> = {
  land:  '#5a8c3e',
  water: '#3a7ec8',
  tree:  '#2d5e1e',
}

/** Canvas rendering constants. */
export const TILE_SIZE = 16
export const VISION_RADIUS = 3 // must match AGENT_VISION_RADIUS in config.py
