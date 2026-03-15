import { useCallback, useEffect, useRef } from 'react'
import type { AgentState, WorldState } from '../types'
import type { ViewportBounds } from '../hooks/useCamera'
import { AGENT_COLORS, TILE_COLORS, TILE_SIZE } from '../constants'

interface Props {
  world: WorldState
  agents: AgentState[]
  viewport: ViewportBounds
  onNavigate: (worldX: number, worldY: number) => void
}

export default function Minimap({ world, agents, viewport, onNavigate }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const { width, height, tiles } = world

    // Canvas pixel dimensions = world tile dimensions (1 px per tile)
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width
      canvas.height = height
    }

    ctx.clearRect(0, 0, width, height)

    // Draw tiles (1px per tile)
    for (let row = 0; row < height; row++) {
      for (let col = 0; col < width; col++) {
        const tile = tiles[row]?.[col]
        ctx.fillStyle = TILE_COLORS[tile] ?? '#888'
        ctx.fillRect(col, row, 1, 1)
      }
    }

    // Draw agents (2x2 bright dots)
    agents.forEach((agent, idx) => {
      if (!agent.alive) return
      const color = AGENT_COLORS[idx % AGENT_COLORS.length]
      ctx.fillStyle = color
      ctx.fillRect(agent.x, agent.y, 1, 1)
    })

    // Draw viewport rectangle
    const vx = viewport.x / TILE_SIZE
    const vy = viewport.y / TILE_SIZE
    const vw = viewport.w / TILE_SIZE
    const vh = viewport.h / TILE_SIZE

    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 0.5
    ctx.strokeRect(vx, vy, vw, vh)
  }, [world, agents, viewport])

  useEffect(() => { draw() }, [draw])

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    const tileX = (e.clientX - rect.left) * scaleX
    const tileY = (e.clientY - rect.top) * scaleY
    onNavigate(tileX * TILE_SIZE, tileY * TILE_SIZE)
  }, [onNavigate])

  return (
    <div className="minimap-container" title="Click to navigate">
      <canvas ref={canvasRef} onClick={handleClick} />
    </div>
  )
}
