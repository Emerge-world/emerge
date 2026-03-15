import { useCallback, useEffect, useRef } from 'react'
import type { AgentState, WorldState } from '../types'
import { STAT_COLORS, TILE_SIZE, VISION_RADIUS } from '../constants'
import { useCamera } from '../hooks/useCamera'
import type { ViewportBounds } from '../hooks/useCamera'
import { generateTileAtlas, getTileRect, TILE_VARIANTS } from '../rendering/tileAtlas'
import { generateAgentAtlas, getAgentRect } from '../rendering/agentSprites'
import { loadExternalTileAtlas, loadExternalAgentAtlas } from '../rendering/assetLoader'

const FRUIT_COLOR = '#facc15'

interface Props {
  world: WorldState
  agents: AgentState[]
  selectedAgentId: number | null
  onAgentClick: (id: number) => void
  onViewportChange?: (bounds: ViewportBounds) => void
  navigateRef?: React.MutableRefObject<((wx: number, wy: number) => void) | null>
}

export default function WorldCanvas({ world, agents, selectedAgentId, onAgentClick, onViewportChange, navigateRef }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  // Tile & agent atlases (procedural fallback, upgraded by external assets)
  const tileAtlasRef = useRef<OffscreenCanvas | HTMLCanvasElement | null>(null)
  const agentAtlasRef = useRef<OffscreenCanvas | HTMLCanvasElement | null>(null)

  // Camera hook
  const camera = useCamera(world.width, world.height, containerRef)

  // Expose navigate function for minimap
  useEffect(() => {
    if (navigateRef) {
      navigateRef.current = camera.navigateTo
    }
  }, [navigateRef, camera.navigateTo])

  // Store latest props in refs for the rAF loop
  const worldRef = useRef(world)
  const agentsRef = useRef(agents)
  const selectedRef = useRef(selectedAgentId)
  worldRef.current = world
  agentsRef.current = agents
  selectedRef.current = selectedAgentId

  // Generate procedural atlases immediately, then try external assets
  useEffect(() => {
    // Procedural atlases are instant — render immediately
    tileAtlasRef.current = generateTileAtlas()
    agentAtlasRef.current = generateAgentAtlas()
    camera.markDirty()

    // Load external assets (higher quality) — replace procedural when ready
    loadExternalTileAtlas().then(atlas => {
      if (atlas) {
        tileAtlasRef.current = atlas
        camera.markDirty()
      }
    })
    loadExternalAgentAtlas().then(atlas => {
      if (atlas) {
        agentAtlasRef.current = atlas
        camera.markDirty()
      }
    })
  }, [camera.markDirty])

  // Mark dirty when data changes
  useEffect(() => { camera.markDirty() }, [world, agents, selectedAgentId, camera.markDirty])

  // Attach wheel listener (non-passive for preventDefault)
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    el.addEventListener('wheel', camera.handleWheel, { passive: false })
    return () => el.removeEventListener('wheel', camera.handleWheel)
  }, [camera.handleWheel])

  // rAF draw loop
  useEffect(() => {
    let rafId: number

    function draw() {
      rafId = requestAnimationFrame(draw)

      if (!camera.dirtyRef.current) return
      camera.dirtyRef.current = false

      const canvas = canvasRef.current
      const container = containerRef.current
      if (!canvas || !container) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const dpr = window.devicePixelRatio || 1
      const viewW = container.clientWidth
      const viewH = container.clientHeight

      // Resize canvas to match container
      if (canvas.width !== viewW * dpr || canvas.height !== viewH * dpr) {
        canvas.width = viewW * dpr
        canvas.height = viewH * dpr
        canvas.style.width = `${viewW}px`
        canvas.style.height = `${viewH}px`
      }

      const w = worldRef.current
      const ag = agentsRef.current
      const selId = selectedRef.current
      const cam = camera.cameraRef.current
      const tileAtlas = tileAtlasRef.current
      const agentAtlas = agentAtlasRef.current

      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      // Disable smoothing for crisp pixel art
      ctx.imageSmoothingEnabled = false

      // Apply DPR + camera transform
      ctx.setTransform(
        dpr * cam.zoom, 0,
        0, dpr * cam.zoom,
        -cam.x * cam.zoom * dpr,
        -cam.y * cam.zoom * dpr,
      )

      // Culling: visible tile range
      const startCol = Math.max(0, Math.floor(cam.x / TILE_SIZE))
      const startRow = Math.max(0, Math.floor(cam.y / TILE_SIZE))
      const endCol = Math.min(w.width - 1, Math.ceil((cam.x + viewW / cam.zoom) / TILE_SIZE))
      const endRow = Math.min(w.height - 1, Math.ceil((cam.y + viewH / cam.zoom) / TILE_SIZE))

      // --- Draw tiles ---
      for (let row = startRow; row <= endRow; row++) {
        for (let col = startCol; col <= endCol; col++) {
          const tile = w.tiles[row]?.[col]
          if (!tile) continue
          const px = col * TILE_SIZE
          const py = row * TILE_SIZE

          if (tileAtlas) {
            const variant = ((col * 7 + row * 13) % TILE_VARIANTS)
            const [sx, sy, sw, sh] = getTileRect(tile, variant)
            ctx.drawImage(tileAtlas, sx, sy, sw, sh, px, py, TILE_SIZE, TILE_SIZE)
          }

          // Fruit indicator
          const res = w.resources[`${col},${row}`]
          if (res && res.quantity > 0) {
            ctx.fillStyle = FRUIT_COLOR
            ctx.beginPath()
            ctx.arc(px + TILE_SIZE - 4, py + 4, 2, 0, Math.PI * 2)
            ctx.fill()
            // Leaf
            ctx.fillStyle = '#4ade80'
            ctx.fillRect(px + TILE_SIZE - 3, py + 2, 2, 1)
          }
        }
      }

      // --- Vision overlay for selected agent ---
      const selected = selId !== null ? ag.find(a => a.id === selId) : null
      if (selected && selected.alive) {
        const r = VISION_RADIUS
        const vx = (selected.x - r) * TILE_SIZE
        const vy = (selected.y - r) * TILE_SIZE
        const vw = (r * 2 + 1) * TILE_SIZE
        const vh = (r * 2 + 1) * TILE_SIZE

        ctx.fillStyle = 'rgba(255, 255, 255, 0.08)'
        ctx.fillRect(vx, vy, vw, vh)
        ctx.strokeStyle = 'rgba(212, 168, 67, 0.6)'
        ctx.lineWidth = 1 / cam.zoom
        ctx.strokeRect(vx + 0.5, vy + 0.5, vw - 1, vh - 1)
      }

      // --- Draw agents ---
      ag.forEach((agent, idx) => {
        const px = agent.x * TILE_SIZE
        const py = agent.y * TILE_SIZE

        if (agentAtlas) {
          // Draw from the sprite atlas
          const [sx, sy, sw, sh] = getAgentRect(idx, agent.alive)
          ctx.drawImage(agentAtlas, sx, sy, sw, sh, px, py, TILE_SIZE, TILE_SIZE)
        }

        if (!agent.alive) return

        // Selection ring (golden glow around tile)
        if (agent.id === selId) {
          ctx.strokeStyle = '#d4a843'
          ctx.lineWidth = 1.5 / cam.zoom
          ctx.strokeRect(px + 0.5, py + 0.5, TILE_SIZE - 1, TILE_SIZE - 1)
        }

        // Hunger warning (red border)
        if (agent.hunger >= 80) {
          ctx.strokeStyle = STAT_COLORS.danger
          ctx.lineWidth = 1 / cam.zoom
          ctx.strokeRect(px, py, TILE_SIZE, TILE_SIZE)
        }

        // Name label above sprite
        ctx.fillStyle = '#ffffff'
        ctx.strokeStyle = '#000000'
        const fontSize = Math.max(4, 5)
        ctx.font = `bold ${fontSize}px monospace`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'bottom'
        ctx.lineWidth = 0.5 / cam.zoom
        const nameX = px + TILE_SIZE / 2
        const nameY = py - 1
        ctx.strokeText(agent.name.slice(0, 3), nameX, nameY)
        ctx.fillText(agent.name.slice(0, 3), nameX, nameY)
      })

      // Notify minimap of viewport bounds
      onViewportChange?.(camera.getViewportBounds())
    }

    rafId = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(rafId)
  }, [camera, onViewportChange])

  // Click handling
  const handleClick = useCallback((e: React.MouseEvent) => {
    if (camera.wasDragging()) return

    const container = containerRef.current
    if (!container) return
    const rect = container.getBoundingClientRect()
    const sx = e.clientX - rect.left
    const sy = e.clientY - rect.top
    const { wx, wy } = camera.screenToWorld(sx, sy)
    const tileX = Math.floor(wx / TILE_SIZE)
    const tileY = Math.floor(wy / TILE_SIZE)

    const clicked = agentsRef.current.find(a => a.alive && a.x === tileX && a.y === tileY)
    if (clicked) {
      onAgentClick(clicked.id)
    }
  }, [camera, onAgentClick])

  return (
    <div
      ref={containerRef}
      className="world-canvas-container"
      onMouseDown={camera.handleMouseDown as unknown as React.MouseEventHandler}
      onMouseMove={camera.handleMouseMove as unknown as React.MouseEventHandler}
      onMouseUp={camera.handleMouseUp as unknown as React.MouseEventHandler}
      onMouseLeave={camera.handleMouseUp as unknown as React.MouseEventHandler}
      onClick={handleClick}
      role="region"
      aria-label="Simulation world"
    >
      <canvas ref={canvasRef} />
    </div>
  )
}

export type { ViewportBounds }
