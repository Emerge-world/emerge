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
  life:   '#4ade80', // --green
  hunger: '#fb923c', // --orange
  energy: '#60a5fa', // --blue
  danger: '#f87171', // --danger
} as const

/** Canvas tile fallback colors (used when tileset.png is not present). */
export const TILE_COLORS: Record<string, string> = {
  land:     '#5a8c3e',
  water:    '#3a7ec8',
  tree:     '#2d5e1e',
  sand:     '#c2b280',
  forest:   '#1a4c0e',
  mountain: '#7a7a7a',
  cave:     '#3a3a3a',
  river:    '#4a90d9',
}

/** Canvas rendering constants. */
export const TILE_SIZE = 16
export const VISION_RADIUS = 3 // must match AGENT_VISION_RADIUS in config.py

/** Zoom bounds */
export const MIN_ZOOM = 0.5
export const MAX_ZOOM = 6.0
export const DEFAULT_ZOOM = 3.0

/** Minimap */
export const MINIMAP_SIZE = 120 // CSS pixels

/** Day/night cycle — mirrored from simulation/config.py */
export const DAY_LENGTH = 24
export const WORLD_START_HOUR = 6
export const SUNSET_START_HOUR = 16
export const NIGHT_START_HOUR = 21

/** Derive the in-world hour from a tick number */
export function tickToHour(tick: number): number {
  return ((tick - 1 + WORLD_START_HOUR) % DAY_LENGTH + DAY_LENGTH) % DAY_LENGTH
}

/** Get the period of day from a tick */
export function tickToPeriod(tick: number): 'day' | 'sunset' | 'night' {
  const hour = tickToHour(tick)
  if (hour >= NIGHT_START_HOUR || hour < WORLD_START_HOUR) return 'night'
  if (hour >= SUNSET_START_HOUR) return 'sunset'
  return 'day'
}
