import type { PanelId } from '../types'
import { tickToHour, tickToPeriod } from '../constants'

interface Props {
  tick: number
  connected: boolean
  paused: boolean
  agentCount: number
  aliveCount: number
  onPause: () => void
  onResume: () => void
  activePanel: PanelId | null
  onSetPanel: (panel: PanelId | null) => void
  minimapSlot?: React.ReactNode
}

export default function HUD({
  tick, connected, paused, agentCount, aliveCount,
  onPause, onResume, activePanel, onSetPanel, minimapSlot,
}: Props) {
  const hour = tickToHour(tick)
  const period = tickToPeriod(tick)

  const periodLabel = period === 'day' ? `${hour}h` : period === 'sunset' ? `${hour}h` : `${hour}h`
  const periodIcon = period === 'day' ? '\u2600' : period === 'sunset' ? '\uD83C\uDF05' : '\uD83C\uDF19'

  function togglePanel(p: PanelId) {
    onSetPanel(activePanel === p ? null : p)
  }

  return (
    <footer className="hud" role="toolbar" aria-label="Simulation controls">
      {/* Minimap slot */}
      <div className="hud-section">
        {minimapSlot}
      </div>

      {/* Stats */}
      <div className="hud-section hud-section--stats" aria-live="polite" aria-atomic="true">
        <span className={`conn-dot ${connected ? 'conn-dot--on' : 'conn-dot--off'}`} aria-hidden="true" />
        <span className="hud-title">EMERGE</span>
        <span className="hud-sep">|</span>
        <span className="hud-label">Tick {tick}</span>
        <span className="hud-sep">|</span>
        <span className="hud-label hud-label--muted">{aliveCount}/{agentCount} alive</span>
        <span className="hud-sep">|</span>
        <span className={`day-indicator day-indicator--${period}`}>
          {periodIcon} {periodLabel}
        </span>
      </div>

      {/* Controls */}
      <div className="hud-section hud-section--controls">
        {paused ? (
          <button className="ctrl-btn ctrl-btn--resume" onClick={onResume} aria-label="Resume simulation">
            &#x25B6; Resume
          </button>
        ) : (
          <button className="ctrl-btn ctrl-btn--pause" onClick={onPause} aria-label="Pause simulation">
            &#x23F8; Pause
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="hud-section hud-section--tabs">
        <button
          className={`tab-btn ${activePanel === 'agents' ? 'tab-btn--active' : ''}`}
          onClick={() => togglePanel('agents')}
          aria-pressed={activePanel === 'agents'}
        >
          Agents
        </button>
        <button
          className={`tab-btn ${activePanel === 'log' ? 'tab-btn--active' : ''}`}
          onClick={() => togglePanel('log')}
          aria-pressed={activePanel === 'log'}
        >
          Log
        </button>
        <button
          className={`tab-btn ${activePanel === 'world' ? 'tab-btn--active' : ''}`}
          onClick={() => togglePanel('world')}
          aria-pressed={activePanel === 'world'}
        >
          World
        </button>
      </div>
    </footer>
  )
}
