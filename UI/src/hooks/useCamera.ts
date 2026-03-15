import { useCallback, useEffect, useRef } from 'react'
import { DEFAULT_ZOOM, MIN_ZOOM, MAX_ZOOM, TILE_SIZE } from '../constants'

export interface Camera {
  x: number  // world-space offset of viewport top-left (in pixels)
  y: number
  zoom: number
}

export interface ViewportBounds {
  x: number
  y: number
  w: number
  h: number
}

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v))
}

/**
 * Camera hook for zoom + pan on the world canvas.
 *
 * Camera state lives in a ref (not useState) to avoid re-renders on every
 * mouse move. The canvas draw loop reads from the ref directly.
 */
export function useCamera(worldWidth: number, worldHeight: number, containerRef: React.RefObject<HTMLDivElement | null>) {
  const cameraRef = useRef<Camera>({ x: 0, y: 0, zoom: DEFAULT_ZOOM })
  const isPanning = useRef(false)
  const panStart = useRef({ x: 0, y: 0 })
  const panThreshold = useRef(false) // true once drag exceeds threshold
  const dirtyRef = useRef(true)

  const markDirty = useCallback(() => { dirtyRef.current = true }, [])

  // Fit world to viewport on mount / resize
  const fitToViewport = useCallback(() => {
    const el = containerRef.current
    if (!el || worldWidth === 0 || worldHeight === 0) return

    const viewW = el.clientWidth
    const viewH = el.clientHeight
    const worldPxW = worldWidth * TILE_SIZE
    const worldPxH = worldHeight * TILE_SIZE

    const zoom = clamp(
      Math.min(viewW / worldPxW, viewH / worldPxH),
      MIN_ZOOM,
      MAX_ZOOM,
    )

    // Center the world
    cameraRef.current = {
      x: (worldPxW / 2) - (viewW / 2 / zoom),
      y: (worldPxH / 2) - (viewH / 2 / zoom),
      zoom,
    }
    markDirty()
  }, [worldWidth, worldHeight, containerRef, markDirty])

  useEffect(() => {
    fitToViewport()
    window.addEventListener('resize', fitToViewport)
    return () => window.removeEventListener('resize', fitToViewport)
  }, [fitToViewport])

  // Zoom toward cursor
  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault()
    const el = containerRef.current
    if (!el) return

    const cam = cameraRef.current
    const rect = el.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top

    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
    const newZoom = clamp(cam.zoom * factor, MIN_ZOOM, MAX_ZOOM)

    // Keep world point under cursor fixed
    const wx = mx / cam.zoom + cam.x
    const wy = my / cam.zoom + cam.y
    cameraRef.current = {
      x: wx - mx / newZoom,
      y: wy - my / newZoom,
      zoom: newZoom,
    }
    markDirty()
  }, [containerRef, markDirty])

  const handleMouseDown = useCallback((e: MouseEvent) => {
    // Left or middle click starts pan
    if (e.button === 0 || e.button === 1) {
      isPanning.current = true
      panThreshold.current = false
      panStart.current = { x: e.clientX, y: e.clientY }
    }
  }, [])

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isPanning.current) return

    const dx = e.clientX - panStart.current.x
    const dy = e.clientY - panStart.current.y

    // Only start panning after 3px threshold (to distinguish from click)
    if (!panThreshold.current) {
      if (Math.abs(dx) < 3 && Math.abs(dy) < 3) return
      panThreshold.current = true
    }

    const cam = cameraRef.current
    cameraRef.current = {
      ...cam,
      x: cam.x - dx / cam.zoom,
      y: cam.y - dy / cam.zoom,
    }
    panStart.current = { x: e.clientX, y: e.clientY }
    markDirty()
  }, [markDirty])

  const handleMouseUp = useCallback(() => {
    isPanning.current = false
  }, [])

  /** Returns true if mouse was dragging (not a click) */
  const wasDragging = useCallback(() => {
    return panThreshold.current
  }, [])

  // Convert screen pixel → world pixel
  const screenToWorld = useCallback((sx: number, sy: number): { wx: number; wy: number } => {
    const cam = cameraRef.current
    return {
      wx: sx / cam.zoom + cam.x,
      wy: sy / cam.zoom + cam.y,
    }
  }, [])

  // Convert world pixel → screen pixel
  const worldToScreen = useCallback((wx: number, wy: number): { sx: number; sy: number } => {
    const cam = cameraRef.current
    return {
      sx: (wx - cam.x) * cam.zoom,
      sy: (wy - cam.y) * cam.zoom,
    }
  }, [])

  // Get the current viewport bounds in world-pixel space
  const getViewportBounds = useCallback((): ViewportBounds => {
    const el = containerRef.current
    if (!el) return { x: 0, y: 0, w: 0, h: 0 }
    const cam = cameraRef.current
    return {
      x: cam.x,
      y: cam.y,
      w: el.clientWidth / cam.zoom,
      h: el.clientHeight / cam.zoom,
    }
  }, [containerRef])

  // Navigate camera to center on a world-pixel position
  const navigateTo = useCallback((worldX: number, worldY: number) => {
    const el = containerRef.current
    if (!el) return
    const cam = cameraRef.current
    cameraRef.current = {
      ...cam,
      x: worldX - el.clientWidth / 2 / cam.zoom,
      y: worldY - el.clientHeight / 2 / cam.zoom,
    }
    markDirty()
  }, [containerRef, markDirty])

  return {
    cameraRef,
    dirtyRef,
    markDirty,
    fitToViewport,
    handleWheel,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    wasDragging,
    screenToWorld,
    worldToScreen,
    getViewportBounds,
    navigateTo,
  }
}
