import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSimulation } from './hooks/useSimulation'
import type { PanelId } from './types'
import type { ViewportBounds } from './hooks/useCamera'
import WorldCanvas from './components/WorldCanvas'
import HUD from './components/HUD'
import Minimap from './components/Minimap'
import AgentDetailPanel from './components/AgentDetailPanel'
import AgentListPanel from './components/AgentListPanel'
import EventLogPanel from './components/EventLogPanel'
import WorldStatsPanel from './components/WorldStatsPanel'

export default function App() {
  const { state, pause, resume } = useSimulation()
  const [activePanel, setActivePanel] = useState<PanelId | null>(null)
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null)
  const [viewport, setViewport] = useState<ViewportBounds>({ x: 0, y: 0, w: 0, h: 0 })

  // Ref for minimap navigation callback (passed to WorldCanvas via camera)
  const navigateRef = useRef<((wx: number, wy: number) => void) | null>(null)

  const aliveCount = state.agents.filter(a => a.alive).length

  // Build agent name → index map for event log coloring
  const agentColorMap = useMemo(() => {
    const map: Record<string, number> = {}
    state.agents.forEach((a, i) => { map[a.name] = i })
    return map
  }, [state.agents])

  // Find selected agent and its index
  const selectedAgentIndex = state.agents.findIndex(a => a.id === selectedAgentId)
  const selectedAgent = selectedAgentIndex >= 0 ? state.agents[selectedAgentIndex] : null

  // Handle agent click from canvas or list
  const handleAgentClick = useCallback((id: number) => {
    setSelectedAgentId(prev => prev === id ? null : id)
  }, [])

  // Handle agent selection from list panel — select and close list
  const handleAgentSelect = useCallback((id: number) => {
    setSelectedAgentId(prev => prev === id ? null : id)
  }, [])

  // Close agent detail
  const handleCloseDetail = useCallback(() => {
    setSelectedAgentId(null)
  }, [])

  // Close tab panel
  const handleClosePanel = useCallback(() => {
    setActivePanel(null)
  }, [])

  // Minimap navigation
  const handleMinimapNavigate = useCallback((wx: number, wy: number) => {
    navigateRef.current?.(wx, wy)
  }, [])

  // Viewport change from WorldCanvas
  const handleViewportChange = useCallback((bounds: ViewportBounds) => {
    setViewport(bounds)
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Don't capture if focus is on an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return

      if (e.key === 'Escape') {
        if (selectedAgentId !== null) {
          setSelectedAgentId(null)
        } else if (activePanel !== null) {
          setActivePanel(null)
        }
      }
      if (e.key === ' ' && !(e.target instanceof HTMLButtonElement)) {
        e.preventDefault()
        state.paused ? resume() : pause()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selectedAgentId, activePanel, state.paused, pause, resume])

  return (
    <div className="app">
      {/* World canvas — fullscreen behind everything */}
      {state.world ? (
        <WorldCanvas
          world={state.world}
          agents={state.agents}
          selectedAgentId={selectedAgentId}
          onAgentClick={handleAgentClick}
          onViewportChange={handleViewportChange}
          navigateRef={navigateRef}
        />
      ) : (
        <div className="world-canvas-container">
          <div className="world-placeholder" aria-live="polite">
            {state.connected
              ? 'Waiting for simulation data...'
              : 'Connecting to server...'}
          </div>
        </div>
      )}

      {/* Connection lost overlay */}
      {!state.connected && state.world && (
        <div className="connection-overlay">
          <span>Reconnecting...</span>
        </div>
      )}

      {/* Agent Detail Panel (when an agent is selected) */}
      {selectedAgent && (
        <AgentDetailPanel
          agent={selectedAgent}
          agentIndex={selectedAgentIndex}
          onClose={handleCloseDetail}
        />
      )}

      {/* Tab panels (only one at a time) */}
      {activePanel === 'agents' && !selectedAgent && (
        <AgentListPanel
          agents={state.agents}
          selectedAgentId={selectedAgentId}
          onSelectAgent={handleAgentSelect}
          onClose={handleClosePanel}
        />
      )}

      {activePanel === 'log' && (
        <EventLogPanel
          events={state.eventLog}
          agentColorMap={agentColorMap}
          onClose={handleClosePanel}
        />
      )}

      {activePanel === 'world' && (
        <WorldStatsPanel
          tick={state.tick}
          world={state.world}
          agents={state.agents}
          onClose={handleClosePanel}
        />
      )}

      {/* HUD bar — always visible at bottom */}
      <HUD
        tick={state.tick}
        connected={state.connected}
        paused={state.paused}
        agentCount={state.agents.length}
        aliveCount={aliveCount}
        onPause={pause}
        onResume={resume}
        activePanel={activePanel}
        onSetPanel={setActivePanel}
        minimapSlot={
          state.world ? (
            <Minimap
              world={state.world}
              agents={state.agents}
              viewport={viewport}
              onNavigate={handleMinimapNavigate}
            />
          ) : undefined
        }
      />
    </div>
  )
}
