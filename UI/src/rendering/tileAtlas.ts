/**
 * Procedural pixel art tile atlas.
 *
 * Generates a single offscreen canvas with all tile types drawn side-by-side
 * at 16x16 pixels each. When a tileset.png is loaded externally, it takes
 * priority; this atlas is the fallback for high-quality rendering without
 * external assets.
 *
 * Atlas layout: each tile occupies 16px wide × 16px tall, arranged
 * horizontally in the order defined by TILE_ORDER.
 */

import { TILE_SIZE } from '../constants'

/** Order of tiles in the atlas — matches SPRITE_MAP keys in WorldCanvas */
export const TILE_ORDER = ['land', 'water', 'tree', 'sand', 'forest', 'mountain', 'cave', 'river'] as const

/** Seeded pseudo-random for deterministic tile textures */
function mulberry32(seed: number) {
  return () => {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed)
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t
    return ((t ^ t >>> 14) >>> 0) / 4294967296
  }
}


type DrawFn = (ctx: CanvasRenderingContext2D, x: number, y: number, rng: () => number) => void

// ── Tile drawing functions ────────────────────────────────────────────

const drawLand: DrawFn = (ctx, x, y, rng) => {
  const S = TILE_SIZE
  // Base grass
  ctx.fillStyle = '#5a8c3e'
  ctx.fillRect(x, y, S, S)

  // Grass texture — darker patches
  for (let i = 0; i < 8; i++) {
    const px = x + Math.floor(rng() * S)
    const py = y + Math.floor(rng() * S)
    ctx.fillStyle = rng() > 0.5 ? '#4e7a34' : '#649840'
    ctx.fillRect(px, py, 1, 1)
  }

  // Tiny grass tufts (lighter highlights)
  for (let i = 0; i < 4; i++) {
    const px = x + Math.floor(rng() * (S - 1))
    const py = y + Math.floor(rng() * (S - 1))
    ctx.fillStyle = '#6ea84a'
    ctx.fillRect(px, py, 1, 1)
    ctx.fillStyle = '#7ab856'
    ctx.fillRect(px, py - 1, 1, 1)
  }

  // Occasional tiny flower
  if (rng() > 0.7) {
    const fx = x + 2 + Math.floor(rng() * (S - 4))
    const fy = y + 2 + Math.floor(rng() * (S - 4))
    const colors = ['#f5e642', '#e87d7d', '#d4a0e8', '#ffffff']
    ctx.fillStyle = colors[Math.floor(rng() * colors.length)]
    ctx.fillRect(fx, fy, 1, 1)
  }
}

const drawWater: DrawFn = (ctx, x, y, rng) => {
  const S = TILE_SIZE
  // Deep water base
  ctx.fillStyle = '#2a6cb8'
  ctx.fillRect(x, y, S, S)

  // Mid-tone variation
  for (let i = 0; i < 12; i++) {
    const px = x + Math.floor(rng() * S)
    const py = y + Math.floor(rng() * S)
    ctx.fillStyle = rng() > 0.5 ? '#3178c4' : '#2460a8'
    ctx.fillRect(px, py, 1 + Math.floor(rng() * 2), 1)
  }

  // Lighter wave crests
  for (let row = 0; row < S; row += 4) {
    const offset = Math.floor(rng() * 4)
    for (let col = offset; col < S; col += 5) {
      ctx.fillStyle = '#5a9cd8'
      ctx.fillRect(x + col, y + row, 2, 1)
    }
  }

  // Bright highlight specks
  for (let i = 0; i < 3; i++) {
    const px = x + Math.floor(rng() * S)
    const py = y + Math.floor(rng() * S)
    ctx.fillStyle = '#8ac4f0'
    ctx.fillRect(px, py, 1, 1)
  }
}

const drawTree: DrawFn = (ctx, x, y, rng) => {
  const S = TILE_SIZE
  // Grass base beneath the tree
  ctx.fillStyle = '#4a7832'
  ctx.fillRect(x, y, S, S)

  // Dark ground shadow beneath canopy
  ctx.fillStyle = '#3d6628'
  ctx.fillRect(x + 2, y + 8, 12, 6)

  // Trunk
  ctx.fillStyle = '#6b4226'
  ctx.fillRect(x + 6, y + 10, 4, 6)
  ctx.fillStyle = '#7d5230'
  ctx.fillRect(x + 7, y + 10, 2, 6)

  // Canopy (layered circles for organic shape)
  const canopyColors = ['#2d5e1e', '#367524', '#2a5419']
  // Main canopy
  ctx.fillStyle = canopyColors[0]
  fillCircle(ctx, x + 8, y + 6, 6)
  // Lighter highlights
  ctx.fillStyle = canopyColors[1]
  fillCircle(ctx, x + 7, y + 5, 4)
  ctx.fillStyle = '#408a30'
  fillCircle(ctx, x + 6, y + 4, 2)

  // Dark detail
  ctx.fillStyle = canopyColors[2]
  ctx.fillRect(x + 10, y + 7, 2, 2)
  ctx.fillRect(x + 4, y + 8, 2, 1)

  // Light leaf specks
  for (let i = 0; i < 3; i++) {
    const px = x + 4 + Math.floor(rng() * 8)
    const py = y + 2 + Math.floor(rng() * 6)
    ctx.fillStyle = '#4aad36'
    ctx.fillRect(px, py, 1, 1)
  }
}

const drawSand: DrawFn = (ctx, x, y, rng) => {
  const S = TILE_SIZE
  ctx.fillStyle = '#c2b280'
  ctx.fillRect(x, y, S, S)

  // Grain variation
  for (let i = 0; i < 10; i++) {
    const px = x + Math.floor(rng() * S)
    const py = y + Math.floor(rng() * S)
    ctx.fillStyle = rng() > 0.5 ? '#b8a874' : '#ccbc8a'
    ctx.fillRect(px, py, 1, 1)
  }

  // Tiny pebbles
  for (let i = 0; i < 2; i++) {
    const px = x + Math.floor(rng() * (S - 1))
    const py = y + Math.floor(rng() * (S - 1))
    ctx.fillStyle = '#a89868'
    ctx.fillRect(px, py, 2, 1)
  }
}

const drawForest: DrawFn = (ctx, x, y, rng) => {
  const S = TILE_SIZE
  // Dark forest floor
  ctx.fillStyle = '#1a4c0e'
  ctx.fillRect(x, y, S, S)

  // Multiple small tree canopies
  const positions = [
    [3, 3], [10, 2], [6, 9], [12, 10], [2, 12],
  ]
  for (const [tx, ty] of positions) {
    ctx.fillStyle = '#245a16'
    fillCircle(ctx, x + tx, y + ty, 3)
    ctx.fillStyle = '#2d6e1c'
    fillCircle(ctx, x + tx - 1, y + ty - 1, 2)
  }

  // Dark gaps between trees
  for (let i = 0; i < 6; i++) {
    const px = x + Math.floor(rng() * S)
    const py = y + Math.floor(rng() * S)
    ctx.fillStyle = '#143c0a'
    ctx.fillRect(px, py, 1, 1)
  }

  // Bright leaf highlights
  for (let i = 0; i < 4; i++) {
    const px = x + Math.floor(rng() * S)
    const py = y + Math.floor(rng() * S)
    ctx.fillStyle = '#3a8c28'
    ctx.fillRect(px, py, 1, 1)
  }
}

const drawMountain: DrawFn = (ctx, x, y, rng) => {
  const S = TILE_SIZE
  // Rocky base
  ctx.fillStyle = '#6a6a6a'
  ctx.fillRect(x, y, S, S)

  // Mountain peak shape (triangle)
  ctx.fillStyle = '#808080'
  for (let row = 0; row < 10; row++) {
    const halfW = Math.floor((10 - row) * 0.7)
    const cx = 8
    ctx.fillRect(x + cx - halfW, y + row + 2, halfW * 2, 1)
  }

  // Snow cap
  ctx.fillStyle = '#e8e8e8'
  for (let row = 0; row < 3; row++) {
    const halfW = Math.max(1, 3 - row)
    ctx.fillRect(x + 8 - halfW, y + 2 + row, halfW * 2, 1)
  }
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(x + 7, y + 2, 2, 1)

  // Rock texture
  for (let i = 0; i < 6; i++) {
    const px = x + Math.floor(rng() * S)
    const py = y + 6 + Math.floor(rng() * (S - 6))
    ctx.fillStyle = rng() > 0.5 ? '#5a5a5a' : '#747474'
    ctx.fillRect(px, py, 1, 1)
  }

  // Dark crevice lines
  ctx.fillStyle = '#4a4a4a'
  ctx.fillRect(x + 6, y + 6, 1, 3)
  ctx.fillRect(x + 9, y + 8, 1, 2)
}

const drawCave: DrawFn = (ctx, x, y, rng) => {
  const S = TILE_SIZE
  // Dark rocky ground
  ctx.fillStyle = '#3a3a3a'
  ctx.fillRect(x, y, S, S)

  // Cave opening (dark center)
  ctx.fillStyle = '#1a1a1a'
  fillCircle(ctx, x + 8, y + 8, 5)
  ctx.fillStyle = '#0a0a0a'
  fillCircle(ctx, x + 8, y + 8, 3)

  // Rocky rim
  const rimColors = ['#4a4a4a', '#555555', '#3e3e3e']
  for (let angle = 0; angle < 8; angle++) {
    const a = (angle / 8) * Math.PI * 2
    const rx = x + 8 + Math.round(Math.cos(a) * 6)
    const ry = y + 8 + Math.round(Math.sin(a) * 6)
    ctx.fillStyle = rimColors[Math.floor(rng() * rimColors.length)]
    ctx.fillRect(rx, ry, 2, 2)
  }

  // Texture variation
  for (let i = 0; i < 5; i++) {
    const px = x + Math.floor(rng() * S)
    const py = y + Math.floor(rng() * S)
    ctx.fillStyle = rng() > 0.5 ? '#2e2e2e' : '#444444'
    ctx.fillRect(px, py, 1, 1)
  }
}

const drawRiver: DrawFn = (ctx, x, y, rng) => {
  const S = TILE_SIZE
  // River water base
  ctx.fillStyle = '#3580c0'
  ctx.fillRect(x, y, S, S)

  // Flow lines (horizontal current)
  for (let row = 2; row < S; row += 3) {
    const offset = Math.floor(rng() * 3)
    ctx.fillStyle = '#5a9cd8'
    for (let col = offset; col < S; col += 4) {
      ctx.fillRect(x + col, y + row, 2, 1)
    }
  }

  // Deeper center channel
  ctx.fillStyle = '#2a6cb8'
  ctx.fillRect(x + 4, y, 8, S)

  // Foam/current lines in center
  ctx.fillStyle = '#7ab8e8'
  for (let row = 1; row < S; row += 4) {
    const col = 5 + Math.floor(rng() * 6)
    ctx.fillRect(x + col, y + row, 3, 1)
  }

  // Edge gradient (lighter banks)
  ctx.fillStyle = '#4890d0'
  ctx.fillRect(x + 3, y, 1, S)
  ctx.fillRect(x + 12, y, 1, S)
}

// ── Helper ────────────────────────────────────────────────────────────

function fillCircle(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  for (let dy = -r; dy <= r; dy++) {
    for (let dx = -r; dx <= r; dx++) {
      if (dx * dx + dy * dy <= r * r) {
        ctx.fillRect(cx + dx, cy + dy, 1, 1)
      }
    }
  }
}

// ── Atlas generator ──────────────────────────────────────────────────

const TILE_DRAW_MAP: Record<string, DrawFn> = {
  land:     drawLand,
  water:    drawWater,
  tree:     drawTree,
  sand:     drawSand,
  forest:   drawForest,
  mountain: drawMountain,
  cave:     drawCave,
  river:    drawRiver,
}

/**
 * Generate a procedural tile atlas.
 *
 * Returns an offscreen canvas where each tile type is drawn at
 * (index * TILE_SIZE, 0) — matching the SPRITE_MAP layout used
 * by WorldCanvas. When tileset.png is available, it overrides this.
 *
 * Multiple variants are generated vertically to reduce visual repetition:
 * rows 0..VARIANTS-1, each with slightly different RNG seeds.
 */
export const TILE_VARIANTS = 4

export function generateTileAtlas(): OffscreenCanvas | HTMLCanvasElement {
  const width = TILE_ORDER.length * TILE_SIZE
  const height = TILE_VARIANTS * TILE_SIZE

  let canvas: OffscreenCanvas | HTMLCanvasElement
  try {
    canvas = new OffscreenCanvas(width, height)
  } catch {
    canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
  }

  const ctx = canvas.getContext('2d') as CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D
  if (!ctx) return canvas

  TILE_ORDER.forEach((tile, col) => {
    const drawFn = TILE_DRAW_MAP[tile]
    if (!drawFn) return
    for (let variant = 0; variant < TILE_VARIANTS; variant++) {
      const rng = mulberry32(col * 1000 + variant * 7 + 42)
      drawFn(ctx as CanvasRenderingContext2D, col * TILE_SIZE, variant * TILE_SIZE, rng)
    }
  })

  return canvas
}

/**
 * Get the atlas source rect for a given tile type and variant.
 * Returns [sx, sy, sw, sh] matching SPRITE_MAP format.
 */
export function getTileRect(tile: string, variant: number): [number, number, number, number] {
  const idx = TILE_ORDER.indexOf(tile as typeof TILE_ORDER[number])
  const col = idx >= 0 ? idx : 0
  const row = variant % TILE_VARIANTS
  return [col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE]
}
