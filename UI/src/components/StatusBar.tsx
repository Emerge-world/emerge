interface Props {
  tick: number
  connected: boolean
  paused: boolean
  agentCount: number
  aliveCount: number
  onPause: () => void
  onResume: () => void
  panelOpen: boolean
  onTogglePanel: () => void
}

export default function StatusBar({
  tick,
  connected,
  paused,
  agentCount,
  aliveCount,
  onPause,
  onResume,
  panelOpen,
  onTogglePanel,
}: Props) {
  return (
    <header className="status-bar" role="banner">
      {/* Left: connection pill */}
      <div className="status-section">
        <span
          className={`conn-dot ${connected ? 'conn-dot--on' : 'conn-dot--off'}`}
          aria-hidden="true"
        />
        <span className="conn-label" aria-live="assertive">
          {connected ? 'Live' : 'Connecting…'}
        </span>
      </div>

      {/* Centre: tick + agent count */}
      <div className="status-section status-section--centre">
        <span className="status-title">Emerge</span>
        <span className="status-sep" aria-hidden="true">|</span>
        <span className="tick-label" aria-live="polite" aria-atomic="true">
          Tick {tick}
        </span>
        <span className="status-sep" aria-hidden="true">|</span>
        <span className="agent-count" aria-live="polite" aria-atomic="true">
          {aliveCount}/{agentCount} alive
        </span>
      </div>

      {/* Right: controls */}
      <div className="status-section status-section--right">
        {paused ? (
          <button
            className="ctrl-btn ctrl-btn--resume"
            onClick={onResume}
            aria-label="Resume simulation"
          >
            ▶ Resume
          </button>
        ) : (
          <button
            className="ctrl-btn ctrl-btn--pause"
            onClick={onPause}
            aria-label="Pause simulation"
          >
            ⏸ Pause
          </button>
        )}

        {/* Panel toggle — visible only on mobile via CSS */}
        <button
          className="ctrl-btn ctrl-btn--panel-toggle"
          onClick={onTogglePanel}
          aria-label={panelOpen ? 'Hide agent panel' : 'Show agent panel'}
          aria-expanded={panelOpen}
        >
          {panelOpen ? '✕' : '☰'}
        </button>
      </div>
    </header>
  )
}
