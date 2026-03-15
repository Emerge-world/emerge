/**
 * Procedural pixel art agent sprites.
 *
 * Generates a small top-down humanoid character for each agent color.
 * Each sprite is 16x16 pixels with:
 * - Colored outfit (shirt/tunic)
 * - Skin-toned head with simple eyes
 * - Dark hair
 * - Slight shadow beneath
 *
 * When external character spritesheets are loaded, they override these.
 */

import { AGENT_COLORS, TILE_SIZE } from '../constants'

/** Template pixel art for a top-down character (16x16).
 *  Legend:
 *    . = transparent
 *    S = shadow
 *    H = hair (dark)
 *    K = skin
 *    E = eye (dark)
 *    C = cloth (agent color)
 *    D = cloth dark (agent color shade)
 *    B = boot (dark brown)
 *    W = white (eye white)
 */
const CHAR_TEMPLATE = [
  '................',
  '................',
  '.....HHHH.......',
  '....HHHHHH......',
  '....HKKKKH......',
  '....KWEWEK......',
  '....KKKKKK......',
  '.....KKKK.......',
  '....CCCCCC......',
  '....CDCCDC......',
  '....CCCCCC......',
  '....CCCCCC......',
  '....DC..CD......',
  '....BB..BB......',
  '....BB..BB......',
  '..SS......SS....',
]

interface ColorMap {
  S: string  // shadow
  H: string  // hair
  K: string  // skin
  E: string  // eye
  W: string  // eye white
  C: string  // cloth main
  D: string  // cloth dark
  B: string  // boots
}

function hexToRgb(hex: string): [number, number, number] {
  const v = parseInt(hex.slice(1), 16)
  return [(v >> 16) & 0xff, (v >> 8) & 0xff, v & 0xff]
}

function darken(hex: string, amount: number): string {
  const [r, g, b] = hexToRgb(hex)
  const f = 1 - amount
  return '#' + ((1 << 24) +
    (Math.max(0, Math.round(r * f)) << 16) +
    (Math.max(0, Math.round(g * f)) << 8) +
    Math.max(0, Math.round(b * f))
  ).toString(16).slice(1)
}

function makeColorMap(agentColor: string): ColorMap {
  return {
    S: 'rgba(0,0,0,0.25)',
    H: '#2c1810',
    K: '#f0c8a0',
    E: '#1a1a2e',
    W: '#ffffff',
    C: agentColor,
    D: darken(agentColor, 0.3),
    B: '#3d2817',
  }
}

// Hair color variations based on agent index
const HAIR_COLORS = [
  '#2c1810', // dark brown
  '#1a1a2e', // black
  '#8b6040', // light brown
  '#c8a050', // blonde
  '#a03020', // red
  '#3d2817', // chestnut
  '#606060', // grey
  '#f0d890', // platinum
  '#4a2810', // auburn
  '#2a2a3a', // dark blue-black
]

const SKIN_TONES = [
  '#f0c8a0', // light
  '#d4a878', // medium
  '#c08860', // tan
  '#e8c098', // fair
  '#b87848', // brown
]

/**
 * Generate a sprite atlas with one character sprite per agent color.
 *
 * Layout: each agent sprite at (index * TILE_SIZE, 0).
 * Alive sprites on row 0, dead sprites (grey X) on row 1.
 */
export function generateAgentAtlas(): OffscreenCanvas | HTMLCanvasElement {
  const count = AGENT_COLORS.length
  const width = count * TILE_SIZE
  const height = TILE_SIZE * 2 // row 0 = alive, row 1 = dead

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

  AGENT_COLORS.forEach((color, idx) => {
    const ox = idx * TILE_SIZE

    // Build color map with varied hair/skin per agent
    const cm = makeColorMap(color)
    cm.H = HAIR_COLORS[idx % HAIR_COLORS.length]
    cm.K = SKIN_TONES[idx % SKIN_TONES.length]

    // Draw alive sprite (row 0)
    drawCharacter(ctx as CanvasRenderingContext2D, ox, 0, cm)

    // Draw dead sprite (row 1) — grey X
    drawDeadMarker(ctx as CanvasRenderingContext2D, ox, TILE_SIZE)
  })

  return canvas
}

function drawCharacter(ctx: CanvasRenderingContext2D, ox: number, oy: number, cm: ColorMap) {
  const colorLookup: Record<string, string> = {
    S: cm.S, H: cm.H, K: cm.K, E: cm.E, W: cm.W,
    C: cm.C, D: cm.D, B: cm.B,
  }

  for (let row = 0; row < CHAR_TEMPLATE.length; row++) {
    const line = CHAR_TEMPLATE[row]
    for (let col = 0; col < line.length; col++) {
      const ch = line[col]
      if (ch === '.') continue
      const fill = colorLookup[ch]
      if (!fill) continue
      ctx.fillStyle = fill
      ctx.fillRect(ox + col, oy + row, 1, 1)
    }
  }
}

function drawDeadMarker(ctx: CanvasRenderingContext2D, ox: number, oy: number) {
  // Grey X mark
  ctx.strokeStyle = '#6b7280'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(ox + 4, oy + 4); ctx.lineTo(ox + 12, oy + 12)
  ctx.moveTo(ox + 12, oy + 4); ctx.lineTo(ox + 4, oy + 12)
  ctx.stroke()
}

/**
 * Get the atlas source rect for an agent sprite.
 * @param agentIndex — index in the agents array
 * @param alive — true for alive sprite, false for dead marker
 * @returns [sx, sy, sw, sh]
 */
export function getAgentRect(agentIndex: number, alive: boolean): [number, number, number, number] {
  const col = agentIndex % AGENT_COLORS.length
  const row = alive ? 0 : 1
  return [col * TILE_SIZE, row * TILE_SIZE, TILE_SIZE, TILE_SIZE]
}
