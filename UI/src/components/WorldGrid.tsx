/**
 * WorldGrid — Canvas-based top-down renderer.
 *
 * Tile rendering:
 *   1. Tries to load `assets/tileset.png` from the public folder.
 *      If it exists, draws sprites using SPRITE_MAP coordinates.
 *   2. Falls back to solid colored rectangles if the image is missing.
 *
 * Kenney tileset setup (optional):
 *   Download any Kenney top-down tileset (e.g. "Tiny Town" at kenney.nl).
 *   Place the PNG at:  UI/public/assets/tileset.png
 *   Then update TILE_SIZE and SPRITE_MAP below to match the actual sheet layout.
 *
 * Sprite map format: { tileType: [sx, sy, sw, sh] } — source rect in the PNG.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { AgentState, WorldState } from '../types'
import { AGENT_COLORS, STAT_COLORS, TILE_COLORS, TILE_SIZE, VISION_RADIUS } from '../constants'

// ---------------------------------------------------------------------------
// Sprite map — adjust to match your Kenney tileset
// ---------------------------------------------------------------------------

// Source rectangles [sx, sy, sw, sh] in the tileset PNG.
// These defaults assume a 16×16 sheet with tiles arranged in a grid.
// Update sx/sy to point at the correct sprites in your chosen sheet.
const SPRITE_MAP: Record<string, [number, number, number, number]> = {
  land:  [  0,  0, 16, 16],
  water: [ 16,  0, 16, 16],
  tree:  [ 32,  0, 16, 16],
}

// Canvas colors — mirror CSS tokens for consistency
const FRUIT_COLOR = '#facc15'    // --fruit
const DISABLED_COLOR = '#6b7280' // --disabled

interface Props {
  world: WorldState
  agents: AgentState[]
  selectedAgentId: number | null
  onAgentClick: (id: number) => void
}

export default function WorldGrid({ world, agents, selectedAgentId, onAgentClick }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const tilesetRef = useRef<HTMLImageElement | null>(null)
  const [tilesetReady, setTilesetReady] = useState(false)

  // Load tileset once
  useEffect(() => {
    const img = new Image()
    img.src = '/assets/tileset.png'
    img.onload = () => {
      tilesetRef.current = img
      setTilesetReady(true)
    }
    img.onerror = () => {
      // No tileset — will use colored squares
      setTilesetReady(false)
    }
  }, [])

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const { width, height, tiles, resources } = world
    const tileset = tilesetRef.current

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // --- Draw tiles ---
    for (let row = 0; row < height; row++) {
      for (let col = 0; col < width; col++) {
        const tile = tiles[row][col]
        const px = col * TILE_SIZE
        const py = row * TILE_SIZE

        if (tileset) {
          const [sx, sy, sw, sh] = SPRITE_MAP[tile] ?? SPRITE_MAP.land
          ctx.drawImage(tileset, sx, sy, sw, sh, px, py, TILE_SIZE, TILE_SIZE)
        } else {
          ctx.fillStyle = TILE_COLORS[tile] ?? '#888'
          ctx.fillRect(px, py, TILE_SIZE, TILE_SIZE)
        }

        // Fruit indicator: small yellow dot on tree tiles that still have resources
        if (tile === 'tree' && resources[`${col},${row}`]) {
          ctx.fillStyle = FRUIT_COLOR
          ctx.beginPath()
          ctx.arc(px + TILE_SIZE - 4, py + 4, 3, 0, Math.PI * 2)
          ctx.fill()
        }
      }
    }

    // --- Draw vision overlay for selected agent ---
    const selected = selectedAgentId !== null
      ? agents.find(a => a.id === selectedAgentId)
      : null

    if (selected && selected.alive) {
      const r = VISION_RADIUS
      const vx = (selected.x - r) * TILE_SIZE
      const vy = (selected.y - r) * TILE_SIZE
      const vw = (r * 2 + 1) * TILE_SIZE
      const vh = (r * 2 + 1) * TILE_SIZE

      ctx.fillStyle = 'rgba(255, 255, 255, 0.12)'
      ctx.fillRect(vx, vy, vw, vh)
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)'
      ctx.lineWidth = 1.5
      ctx.strokeRect(vx + 0.75, vy + 0.75, vw - 1.5, vh - 1.5)
    }

    // --- Draw agents ---
    agents.forEach((agent, idx) => {
      const cx = agent.x * TILE_SIZE + TILE_SIZE / 2
      const cy = agent.y * TILE_SIZE + TILE_SIZE / 2
      const color = AGENT_COLORS[idx % AGENT_COLORS.length]
      const radius = TILE_SIZE / 2 - 1

      if (!agent.alive) {
        // Dead: grey X
        ctx.strokeStyle = DISABLED_COLOR
        ctx.lineWidth = 1.5
        ctx.beginPath()
        ctx.moveTo(cx - 4, cy - 4); ctx.lineTo(cx + 4, cy + 4)
        ctx.moveTo(cx + 4, cy - 4); ctx.lineTo(cx - 4, cy + 4)
        ctx.stroke()
        return
      }

      // Circle
      ctx.beginPath()
      ctx.arc(cx, cy, radius, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.fill()

      // Selection ring
      if (agent.id === selectedAgentId) {
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 2
        ctx.stroke()
      }

      // Hunger warning: red pulse border
      if (agent.hunger >= 80) {
        ctx.strokeStyle = STAT_COLORS.danger
        ctx.lineWidth = 1.5
        ctx.stroke()
      }

      // Name label (tiny, centred above the circle)
      ctx.fillStyle = '#ffffff'
      ctx.font = `bold ${TILE_SIZE * 0.55}px monospace`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'bottom'
      ctx.fillText(agent.name[0], cx, cy - radius)
    })
  }, [world, agents, selectedAgentId])

  // Redraw whenever state changes
  useEffect(() => {
    draw()
  }, [draw, tilesetReady])

  // Handle click: convert canvas pixel → tile → find agent
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const scaleX = canvas.width / rect.width
      const scaleY = canvas.height / rect.height
      const px = (e.clientX - rect.left) * scaleX
      const py = (e.clientY - rect.top) * scaleY
      const tileX = Math.floor(px / TILE_SIZE)
      const tileY = Math.floor(py / TILE_SIZE)

      const clicked = agents.find(a => a.alive && a.x === tileX && a.y === tileY)
      if (clicked) {
        onAgentClick(clicked.id)
      }
    },
    [agents, onAgentClick],
  )

  const canvasW = world.width * TILE_SIZE
  const canvasH = world.height * TILE_SIZE

  // Build a screen-reader description of agent positions
  const aliveAgents = agents.filter(a => a.alive)
  const srDescription = aliveAgents.length > 0
    ? `${world.width} by ${world.height} tile world with ${aliveAgents.length} alive agents: ${aliveAgents.map(a => `${a.name} at ${a.x},${a.y}`).join('; ')}`
    : `${world.width} by ${world.height} tile world with no alive agents`

  return (
    <canvas
      ref={canvasRef}
      width={canvasW}
      height={canvasH}
      onClick={handleClick}
      style={{ cursor: 'crosshair', display: 'block', imageRendering: 'pixelated' }}
      role="img"
      aria-label={srDescription}
    />
  )
}
