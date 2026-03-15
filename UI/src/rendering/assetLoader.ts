/**
 * External asset loader for Pixel Crawler tiles and TotusLotus characters.
 *
 * Loads PNG spritesheets from the downloaded asset packs and composites them
 * into atlas format matching the procedural atlas layout used by WorldCanvas.
 * Falls back gracefully if assets are unavailable.
 *
 * Atlas formats:
 *   Tiles:  TILE_ORDER.length cols × TILE_VARIANTS rows, each cell 16×16
 *   Agents: AGENT_COLORS.length cols × 2 rows (alive / dead), each cell 16×16
 */

import { AGENT_COLORS, TILE_SIZE } from '../constants'
import { TILE_ORDER, TILE_VARIANTS } from './tileAtlas'

// ── Image loader ──────────────────────────────────────────────────────

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.src = src
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`Failed to load: ${src}`))
  })
}

// ── Asset paths ───────────────────────────────────────────────────────

const PX = '/assets/Pixel Crawler - Free Pack'

const IMG_SOURCES: Record<string, string> = {
  floors:     `${PX}/Environment/Tilesets/Floors_Tiles.png`,
  water:      `${PX}/Environment/Tilesets/Water_tiles.png`,
  dungeon:    `${PX}/Environment/Tilesets/Dungeon_Tiles.png`,
  vegetation: `${PX}/Environment/Props/Static/Vegetation.png`,
  rocks:      `${PX}/Environment/Props/Static/Rocks.png`,
}

const CHARACTER_COUNT = 10

// ── Tile source coordinate mapping ────────────────────────────────────
//
// Each tile type has 4 variants (rows in the atlas).
// Each variant specifies a base tile and an optional overlay.
//
// Source images and their layouts (all 16×16 grid):
//   Floors_Tiles.png  400×416  (25 cols × 26 rows)
//     Col groups: grass(0–79), dirt(80–159), sand(160–239), stone(240–319), dark(320–399)
//   Water_tiles.png   400×400  (25 cols × 25 rows)
//   Dungeon_Tiles.png 400×400  (25 cols × 25 rows)
//   Vegetation.png    400×432  (25 cols × 27 rows)
//   Rocks.png         208×304  (13 cols × 19 rows)
//
// ⚠ ADJUST coordinates below if a tile looks wrong — each pair
//   points to the top-left corner of a 16×16 tile in the source.

const S = TILE_SIZE

interface TileVariant {
  /** Source image key */
  base: string
  /** Base tile source x */
  bx: number
  /** Base tile source y */
  by: number
  /** Overlay image key (optional) */
  over?: string
  /** Overlay source x */
  ox?: number
  /** Overlay source y */
  oy?: number
  /** Overlay source width (defaults to TILE_SIZE) */
  ow?: number
  /** Overlay source height (defaults to TILE_SIZE) */
  oh?: number
}

function tv(base: string, bx: number, by: number): TileVariant
function tv(base: string, bx: number, by: number, over: string, ox: number, oy: number, ow?: number, oh?: number): TileVariant
function tv(base: string, bx: number, by: number, over?: string, ox?: number, oy?: number, ow?: number, oh?: number): TileVariant {
  if (over) return { base, bx, by, over, ox, oy, ow, oh }
  return { base, bx, by }
}

/**
 * Source coordinate map for each tile type × 4 variants.
 *
 * Floors_Tiles.png autotile layout (per terrain, 5 cols wide):
 *   Row 0-1: outer edge transitions (white star shapes)
 *   Row 2-3: inner edge transitions
 *   Row 4+:  center / filled tiles
 *
 * Coordinates below target the "center" (fully filled) tiles
 * for each terrain type.
 */
const TILE_VARIANTS_MAP: Record<string, TileVariant[]> = {
  // Grass: solid green tiles at y=160-176 in grass column (100% opaque, verified)
  land: [
    tv('floors', 16, 160),
    tv('floors', 32, 160),
    tv('floors', 48, 160),
    tv('floors', 16, 176),
  ],

  // Water: solid blue tiles from row 0 of Water_tiles.png (100% opaque)
  water: [
    tv('water', 0,  0),
    tv('water', 80, 0),
    tv('water', 96, 0),
    tv('water', 0,  0),
  ],

  // Tree: solid grass base + bush overlay (77-88% opaque green sprites)
  tree: [
    tv('floors', 16, 160, 'vegetation', 16, 64),
    tv('floors', 32, 160, 'vegetation', 64, 64),
    tv('floors', 48, 160, 'vegetation', 16, 96),
    tv('floors', 16, 176, 'vegetation', 64, 96),
  ],

  // Sand: warm orange-tan tiles at y=384 in Floors_Tiles.png (100% opaque)
  sand: [
    tv('floors', 80,  384),
    tv('floors', 96,  384),
    tv('floors', 112, 384),
    tv('floors', 128, 384),
  ],

  // Forest: solid grass base + bright dense vegetation overlay (88% coverage, avgG=117)
  forest: [
    tv('floors', 16, 160, 'vegetation', 16, 32),
    tv('floors', 32, 160, 'vegetation', 64, 32),
    tv('floors', 48, 160, 'vegetation', 16, 64),
    tv('floors', 16, 176, 'vegetation', 64, 64),
  ],

  // Mountain: beige stone base + grey rock overlay from Rocks.png (row 1+, row 0 is palette)
  mountain: [
    tv('floors', 96,  0, 'rocks', 96,  16),
    tv('floors', 128, 0, 'rocks', 112, 16),
    tv('floors', 80,  16, 'rocks', 96,  16),
    tv('floors', 144, 16, 'rocks', 112, 16),
  ],

  // Cave: dark green mossy dungeon tiles (organic texture, no plank lines)
  cave: [
    tv('dungeon', 176, 16),
    tv('dungeon', 192, 16),
    tv('dungeon', 176, 32),
    tv('dungeon', 192, 32),
  ],

  // River: solid water base (same as water) — flow overlay added in composer
  river: [
    tv('water', 0,  0),
    tv('water', 80, 0),
    tv('water', 96, 0),
    tv('water', 0,  0),
  ],
}

// ── River flow overlay ──────────────────────────────────────────────

/** Draw subtle horizontal flow lines on a river tile to distinguish from still water. */
function drawRiverFlow(ctx: CanvasRenderingContext2D, dx: number, dy: number, variant: number) {
  const offset = variant * 2
  // Light current lines
  ctx.fillStyle = 'rgba(255, 255, 255, 0.18)'
  for (let row = 2 + offset; row < S; row += 5) {
    const col = (variant * 3 + row) % 4
    ctx.fillRect(dx + col, dy + row, 3, 1)
    ctx.fillRect(dx + col + 6, dy + row, 2, 1)
  }
  // Subtle darker channel in center
  ctx.fillStyle = 'rgba(0, 30, 80, 0.12)'
  ctx.fillRect(dx + 5, dy, 6, S)
}

// ── Tile atlas composer ───────────────────────────────────────────────

/**
 * Load external tile assets and compose a tile atlas.
 *
 * Returns an offscreen canvas in the same format as generateTileAtlas():
 *   TILE_ORDER.length columns × TILE_VARIANTS rows, each cell TILE_SIZE×TILE_SIZE.
 *
 * Returns null if any required asset fails to load (caller should
 * fall back to the procedural atlas).
 */
export async function loadExternalTileAtlas(): Promise<OffscreenCanvas | HTMLCanvasElement | null> {
  try {
    // Load all source images in parallel
    const keys = Object.keys(IMG_SOURCES)
    const imgs = await Promise.all(keys.map(k => loadImage(IMG_SOURCES[k])))
    const imgMap: Record<string, HTMLImageElement> = {}
    keys.forEach((k, i) => { imgMap[k] = imgs[i] })

    // Create atlas canvas
    const width = TILE_ORDER.length * S
    const height = TILE_VARIANTS * S

    let canvas: OffscreenCanvas | HTMLCanvasElement
    try {
      canvas = new OffscreenCanvas(width, height)
    } catch {
      canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
    }

    const ctx = canvas.getContext('2d') as CanvasRenderingContext2D
    if (!ctx) return null
    ctx.imageSmoothingEnabled = false

    // Draw each tile type × variant
    TILE_ORDER.forEach((tile, col) => {
      const variants = TILE_VARIANTS_MAP[tile]
      if (!variants) return

      for (let vi = 0; vi < TILE_VARIANTS; vi++) {
        const v = variants[vi % variants.length]
        const dx = col * S
        const dy = vi * S

        // Draw base tile
        const baseImg = imgMap[v.base]
        if (baseImg) {
          ctx.drawImage(baseImg, v.bx, v.by, S, S, dx, dy, S, S)
        }

        // Draw overlay on top
        if (v.over && v.ox != null && v.oy != null) {
          const overImg = imgMap[v.over]
          if (overImg) {
            const ow = v.ow ?? S
            const oh = v.oh ?? S
            ctx.drawImage(overImg, v.ox, v.oy, ow, oh, dx, dy, S, S)
          }
        }

        // River: add flow lines to differentiate from still water
        if (tile === 'river') {
          drawRiverFlow(ctx, dx, dy, vi)
        }
      }
    })

    return canvas
  } catch (e) {
    console.warn('External tile assets unavailable, using procedural atlas:', e)
    return null
  }
}

// ── Agent atlas composer ──────────────────────────────────────────────

/**
 * Load TotusLotus character idle sprites and compose an agent atlas.
 *
 * Each idle spritesheet is 48×32 = 3 cols × 2 rows of 16×16 frames.
 * We take the first frame (0, 0) as the standing sprite.
 *
 * Returns an offscreen canvas in the same format as generateAgentAtlas():
 *   AGENT_COLORS.length columns × 2 rows (alive=0, dead=1), each TILE_SIZE×TILE_SIZE.
 *
 * Returns null if assets can't be loaded.
 */
export async function loadExternalAgentAtlas(): Promise<OffscreenCanvas | HTMLCanvasElement | null> {
  try {
    // Load all 10 character idle sheets
    const sheets = await Promise.all(
      Array.from({ length: CHARACTER_COUNT }, (_, i) =>
        loadImage(`/assets/spritesheets/${i + 1} idle.png`)
      )
    )

    const count = AGENT_COLORS.length
    const width = count * S
    const height = S * 2

    let canvas: OffscreenCanvas | HTMLCanvasElement
    try {
      canvas = new OffscreenCanvas(width, height)
    } catch {
      canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
    }

    const ctx = canvas.getContext('2d') as CanvasRenderingContext2D
    if (!ctx) return null
    ctx.imageSmoothingEnabled = false

    for (let i = 0; i < count; i++) {
      const sheet = sheets[i % CHARACTER_COUNT]
      const destX = i * S

      // Alive sprite (row 0) — first idle frame at (0, 0, 16, 16)
      ctx.drawImage(sheet, 0, 0, S, S, destX, 0, S, S)

      // Dead marker (row 1) — grey X
      ctx.strokeStyle = '#6b7280'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(destX + 4, S + 4)
      ctx.lineTo(destX + 12, S + 12)
      ctx.moveTo(destX + 12, S + 4)
      ctx.lineTo(destX + 4, S + 12)
      ctx.stroke()
    }

    return canvas
  } catch (e) {
    console.warn('External character sprites unavailable, using procedural atlas:', e)
    return null
  }
}
