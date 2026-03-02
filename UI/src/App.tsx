import { useState } from 'react'
import { useSimulation } from './hooks/useSimulation'
import WorldGrid from './components/WorldGrid'
import AgentPanel from './components/AgentPanel'
import StatusBar from './components/StatusBar'

export default function App() {
  const { state, pause, resume } = useSimulation()
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null)
  const [panelOpen, setPanelOpen] = useState(false)

  const aliveCount = state.agents.filter(a => a.alive).length

  return (
    <div className="app">
      <StatusBar
        tick={state.tick}
        connected={state.connected}
        paused={state.paused}
        agentCount={state.agents.length}
        aliveCount={aliveCount}
        onPause={pause}
        onResume={resume}
        panelOpen={panelOpen}
        onTogglePanel={() => setPanelOpen(prev => !prev)}
      />

      <main className="main-layout">
        {/* World canvas — scrollable if larger than viewport */}
        <div className="world-container" role="region" aria-label="Simulation world">
          {state.world ? (
            <WorldGrid
              world={state.world}
              agents={state.agents}
              selectedAgentId={selectedAgentId}
              onAgentClick={(id) =>
                setSelectedAgentId(prev => (prev === id ? null : id))
              }
            />
          ) : (
            <div className="world-placeholder" aria-live="polite">
              {state.connected
                ? 'Waiting for simulation data…'
                : 'Connecting to server…'}
            </div>
          )}
        </div>

        {/* Agent sidebar / bottom panel */}
        <AgentPanel
          agents={state.agents}
          selectedAgentId={selectedAgentId}
          onSelect={(id) =>
            setSelectedAgentId(prev => (prev === id ? null : id))
          }
          open={panelOpen}
        />
      </main>
    </div>
  )
}
